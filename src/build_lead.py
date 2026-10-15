"""Install the shared moving/turning fire-control fixes in the original code hunk."""
import copy
import struct
from src.build_common import ROOT, WORK, assembler, run_tool
from src.hunk_executable import read_hunks, serialize


def patch_game(game):
    run_tool([assembler(), '-m68000', '-Fhunkexe', '-nosym',
              '-L', WORK / 'lead.lst', '-o', WORK / 'lead.hunk', ROOT / 'src/lead.s'],
             'lead_assembler.log')
    header, segments = read_hunks(game)
    before = copy.deepcopy(segments)
    _, patch = read_hunks((WORK / 'lead.hunk').read_bytes())
    assert len(patch) == 2 and [p['type'] for p in patch] == [1001, 1003]
    extension = bytearray(patch[0]['data'])
    code = bytearray(segments[0]['data'])
    original_size = len(code)
    entry = original_size + struct.unpack_from('>I', extension)[0]
    assert 0 <= entry-original_size < len(extension)
    for target, offsets in patch[0]['reloc'].items():
        assert target in (0, 1)
        for offset in offsets:
            if target == 0:
                value = struct.unpack_from('>I', extension, offset)[0]
                struct.pack_into('>I', extension, offset, value + original_size)
            segments[0]['reloc'].setdefault(0, []).append(original_size + offset)

    changes = []
    def replace(address, expected, replacement, reason):
        offset = address - 0x9c
        expected, replacement = bytes.fromhex(expected), bytes.fromhex(replacement)
        assert len(expected) == len(replacement)
        assert code[offset:offset+len(expected)] == expected, hex(address)
        assert not any(offset <= r < offset+len(expected)
                       for offsets in before[0]['reloc'].values() for r in offsets)
        code[offset:offset+len(expected)] = replacement
        changes.append(dict(original_file_offset=hex(address), before=expected.hex(),
                            after=replacement.hex(), reason=reason))

    replace(0x36c2, '6100017c2a734000',
            '4eb9'+struct.pack('>I', entry).hex()+'4e71', 'Track world sight direction')
    segments[0]['reloc'].setdefault(0, []).append(0x36c4-0x9c)
    # Keep the original relative-angle subtraction and its flags for sound,
    # but do not overwrite the independent world-space lead just calculated.
    replace(0x36e2, '3b400066', '4e714e71', 'Preserve world-space lead; retain traverse sound')
    # All launch-vector terms must use the same base time. The original
    # projectile integrator applies the frame timestep once, after launch.
    replace(0x5748, '61000b3a', '4e714e71', 'Inherit full own X velocity')
    replace(0x5754, '61000b2e', '4e714e71', 'Inherit full own Z velocity')
    code.extend(extension)
    segments[0]['data'] = bytes(code)
    segments[0]['size'] = len(code)
    header['hunks'][0]['size'] = len(code)
    result = serialize(header, segments)
    _, checked = read_hunks(result)
    assert len(checked) == len(before)
    assert checked[0]['data'] == bytes(code)
    assert checked[0]['reloc'] == {k: sorted(v) for k,v in segments[0]['reloc'].items()}
    for old, new in zip(before[1:], checked[1:]):
        assert old.get('data') == new.get('data') and old['size'] == new['size']
        assert {k:sorted(v) for k,v in old['reloc'].items()} == new['reloc']
    report = dict(changes=changes, added_code_bytes=len(extension),
                  world_direction_lead=True, full_own_velocity=True,
                  relative_traverse_sound_preserved=True, unchanged_other_hunks=True)
    return result, report
