"""Build verified vehicle colors and shared lead fixes for the supplied Amiga ADF.

The color stage replaces only enemy-family materials. New IDs avoid changing
the existing palette or any of the 35 existing entries in each material map.
All addresses below are offsets in the original game executable, not the ADF.
"""
from collections import Counter
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.build_common import SOURCE, WORK, write_json
from amitools.binfmt.hunk.HunkReader import HunkReader
from amitools.fs.ADFSVolume import ADFSVolume
from amitools.fs.FSString import FSString
from amitools.fs.blkdev.ADFBlockDevice import ADFBlockDevice

SOURCE_SHA = 'f713c20cb1f012fdce352924067783282814a3ec519515c4d7d939ed14d61275'
MODEL_TABLE = 0x35D64
MAP_TABLE = 0x410D2
ENEMY_POINT = 0x29500
MATERIALS = {4: 35, 6: 36, 12: 37}
# Pen values >= 16 are pairs of alternating pixels; values < 16 are solid.
# Dark green/black, green/dark gray, green/gray for the polygon models.
GREEN_PENS = [0x20, 0x52, 0x82]
# Separate material 38 affects only the enemy family's distant point.
DISTANT_POINT_PEN = 0x06  # Original palette entry 06: brown (#AA5500).


def hunks(blob):
    reader = HunkReader()
    assert reader.read_file_obj('game', BytesIO(blob)) == 0, reader.error_string
    segments = []
    for h in reader.hunks:
        if h['type'] in (1001, 1002, 1003):
            segments.append(dict(h, reloc={}))
        elif h['type'] == 1004:
            segments[-1]['reloc'].update(h['reloc'])
        else:
            assert h['type'] in (1011, 1010), h['type']
    return reader, segments


def open_adf(blob, read_only=True):
    dev = ADFBlockDevice('memory.adf', read_only=read_only, fobj=BytesIO(blob))
    dev.open()
    volume = ADFSVolume(dev)
    volume.open()
    assert volume.valid and volume.boot.valid and volume.root.valid
    return dev, volume


def snapshot(volume):
    result = {}

    def walk(directory):
        for node in directory.get_entries():
            name = str(node.get_node_path_name())
            meta = node.get_meta_info()
            entry = dict(protect=meta.get_protect(),
                         timestamp=str(meta.get_mod_ts()),
                         comment=str(meta.get_comment()))
            if node.is_dir():
                entry['directory'] = True
                walk(node)
            else:
                entry['data'] = bytes(node.get_file_data())
            result[name] = entry
    walk(volume.root_dir)
    return result


def build_game(original):
    reader, segments = hunks(original)
    assert len(segments) == 32
    seg = segments[27]
    base, size = seg['data_file_offset'], seg['size']
    assert (base, size) == (0x1B2F4, 0x263D0)

    def u16(address):
        return struct.unpack_from('>H', original, address)[0]

    def pointer(address):
        assert address - base in seg['reloc'][27], hex(address)
        return base + struct.unpack_from('>I', original, address)[0]

    def levels(model):
        address = pointer(MODEL_TABLE + model * 4)
        result = []
        for _ in range(8):
            limit = u16(address)
            result.append(pointer(address + 2))
            if limit & 0x8000:
                return result
            address += 6
        raise AssertionError('Unterminated model LOD list')

    model_levels = {i: levels(i) for i in range(54)}
    target_ids = [i for i, rows in model_levels.items() if ENEMY_POINT in rows]
    target_shapes = {p for i in target_ids for p in model_levels[i]}
    other_shapes = {p for i in model_levels if i not in target_ids for p in model_levels[i]}
    assert not (target_shapes & other_shapes)

    patched = bytearray(original)
    changes = {}
    records = []

    def replace(address, old, new, reason):
        assert original[address] == old
        if address in changes:
            assert changes[address]['new'] == new
        else:
            changes[address] = dict(offset=hex(address), old=old, new=new, reason=reason)
            patched[address] = new

    for shape in sorted(target_shapes):
        kind = u16(shape + 2) & 0xFF
        if kind == 0:
            continue
        if kind == 3:
            assert shape == ENEMY_POINT and u16(shape + 4) == 4
            replace(shape + 5, 4, 38, 'distant vehicle point')
            continue
        assert kind == 1, (hex(shape), kind)
        count = u16(shape + 20)
        offsets, polygons = pointer(shape + 22), pointer(shape + 44)
        for index in range(count):
            start = polygons + original[offsets + index]
            material = original[start]
            assert material < 35
            record = dict(shape=hex(shape), face=index, offset=hex(start), old=material,
                          new=MATERIALS.get(material, material))
            records.append(record)
            if material in MATERIALS:
                replace(start, material, MATERIALS[material], 'vehicle polygon')
            cursor = start + 1
            while original[cursor] not in (0xFE, 0xFF):
                cursor += 1
                assert cursor - start < 256
            if original[cursor] == 0xFE:
                cursor += 1
                while original[cursor] != 0xFF:
                    material = original[cursor]
                    assert material < 35
                    if material in MATERIALS:
                        replace(cursor, material, MATERIALS[material], 'vehicle detail line')
                    cursor += 2
                    assert cursor - start < 256

    # Append six extended lookup tables to the existing DATA hunk. Its original
    # contents keep their offsets. Existing relocation entries for MAP_TABLE
    # already point into this same hunk, so no new relocations are necessary.
    extra = bytearray()
    maps = []
    for mode in range(6):
        old_address = pointer(MAP_TABLE + mode * 4)
        old_map = original[old_address:old_address + 35]
        additions = [old_map[4], old_map[6], old_map[12], old_map[4]]
        if mode in (2, 4, 5):
            additions = GREEN_PENS + [DISTANT_POINT_PEN]
        elif mode == 3:
            # Keep night shading; replace the original dark red highlight.
            assert additions == [0, 0x80, 0x40, 0]
            additions[2] = 0x20
        new_offset = size + len(extra)
        struct.pack_into('>I', patched, MAP_TABLE + mode * 4, new_offset)
        extra.extend(old_map + bytes(additions))
        maps.append(dict(mode=mode, original=old_map.hex(), additions=additions,
                         hunk_offset=new_offset))
    extra.extend(bytes((-len(extra)) % 4))
    growth = len(extra)
    assert growth == 236
    assert original[0x14 + 27 * 4:0x18 + 27 * 4] == struct.pack('>I', size // 4)
    struct.pack_into('>I', patched, 0x14 + 27 * 4, (size + growth) // 4)
    struct.pack_into('>I', patched, seg['hunk_file_offset'] + 4, (size + growth) // 4)
    insertion = base + size
    patched[insertion:insertion] = extra

    # Verify the result as executable structure, not just a byte diff.
    new_reader, new_segments = hunks(bytes(patched))
    assert len(new_segments) == len(segments)
    for i, (old, new) in enumerate(zip(segments, new_segments)):
        assert old['type'] == new['type'] and old['reloc'] == new['reloc']
        if i != 27:
            assert old.get('data') == new.get('data') and old['size'] == new['size']
        else:
            assert new['size'] == old['size'] + growth
    expected = bytearray(original)
    for address, change in changes.items():
        expected[address] = change['new']
    expected[MAP_TABLE:MAP_TABLE + 24] = patched[MAP_TABLE:MAP_TABLE + 24]
    for address in (0x14 + 27 * 4, seg['hunk_file_offset'] + 4):
        expected[address:address+4] = patched[address:address+4]
    expected[insertion:insertion] = extra
    assert bytes(expected) == bytes(patched)
    # Old material values, which include map/UI colors, are identical in all modes.
    for row in maps:
        address = base + row['hunk_offset']
        assert patched[address:address+35].hex() == row['original']
        if row['mode'] in (0, 1):
            old_map = bytes.fromhex(row['original'])
            assert row['additions'] == [old_map[i] for i in (4, 6, 12, 4)]
    assert patched[0xFEA8:0xFEC8] == original[0xFEA8:0xFEC8]
    return bytes(patched), dict(
        targeted_model_ids=target_ids, targeted_unique_shapes=len(target_shapes),
        material_changes=list(changes.values()),
        change_counts=dict(Counter(c['reason'] for c in changes.values())),
        material_maps=maps, added_bytes=growth, faces=records,
        distant_point_palette_index=DISTANT_POINT_PEN,
        verification=dict(all_code_hunks_unchanged=True, all_relocations_unchanged=True,
                          global_palette_unchanged=True, original_material_mappings_unchanged=True,
                          sensor_material_mappings_unchanged=True,
                          all_non_target_model_data_unchanged=True))


def build_adf():
    """Build entirely from the original ADF; do not read earlier build outputs."""
    source = SOURCE
    original_adf = source.read_bytes()
    assert sha256(original_adf).hexdigest() == SOURCE_SHA, 'Unsupported source disk'
    dev, volume = open_adf(original_adf)
    before = snapshot(volume)
    original_game = bytes(volume.read_file(FSString('game')))
    volume.close()
    dev.close()
    game, report = build_game(original_game)
    from src.build_lead import patch_game
    from src.test_lead import verify
    game, lead_report = patch_game(game)
    lead_report['tests'] = verify(original_game, game)
    report['lead_fix'] = lead_report
    from src.build_clip_edges import patch_game as patch_clip_edges
    from src.test_clip_edges import verify as verify_clip_edges
    game, clip_report = patch_clip_edges(game)
    clip_report['tests'] = verify_clip_edges(original_game, game)
    report['clip_edges_fix'] = clip_report
    from src.build_thermal import patch_game as patch_thermal
    from src.test_thermal import verify as verify_thermal
    game, thermal_report = patch_thermal(game)
    thermal_report['tests'] = verify_thermal(original_game, game)
    report['thermal_fix'] = thermal_report
    from src.build_mi24 import patch_game as patch_mi24
    game, mi24_report = patch_mi24(game)
    report['mi24_fix'] = mi24_report
    for name in ('all_code_hunks_unchanged', 'all_relocations_unchanged'):
        report['verification']['color_patch_'+name] = report['verification'].pop(name)
    report['verification']['code_changes_limited_to_lead_clip_thermal_and_mi24_fixes'] = True
    write_json(WORK / 'lead_tests.json', lead_report)
    write_json(WORK / 'clip_edges_tests.json', clip_report['tests'])
    write_json(WORK / 'thermal_tests.json', thermal_report['tests'])

    dev, volume = open_adf(original_adf, read_only=False)
    node = volume.get_file_path_name(FSString('game'))
    meta = node.get_meta_info()
    node.delete(update_ts=False)
    volume.root_dir.create_file(FSString('game'), game, meta_info=meta, update_ts=False)
    volume.close()
    final_adf = bytes(dev.data)
    dev.close()

    check_dev, check_volume = open_adf(final_adf)
    after = snapshot(check_volume)
    assert before.keys() == after.keys()
    changed_files = []
    for name in before:
        if before[name] != after[name]:
            changed_files.append(name)
            assert name.lower() == 'game'
            assert after[name]['data'] == game
            assert {k:v for k,v in before[name].items() if k != 'data'} == {
                k:v for k,v in after[name].items() if k != 'data'}
    assert changed_files == ['game']
    assert len(final_adf) == len(original_adf) == 901120
    assert final_adf[:1024] == original_adf[:1024]
    check_volume.close()
    check_dev.close()
    assert source.read_bytes() == original_adf
    report.update(source_adf_sha256=SOURCE_SHA, result_adf_sha256=sha256(final_adf).hexdigest(),
                  original_game_sha256=sha256(original_game).hexdigest(),
                  result_game_sha256=sha256(game).hexdigest(), changed_files=changed_files,
                  game_size_before=len(original_game), game_size_after=len(game),
                  full_game_emulator_test=False)
    report['verification'].update(all_other_files_and_metadata_unchanged=True,
                                  boot_blocks_unchanged=True, source_disk_unchanged=True)
    return final_adf, report


def main():
    # Retain the old command as an alias; publish only the complete mod.
    from src.build_zoom_f3 import build
    build()


if __name__ == '__main__':
    main()
