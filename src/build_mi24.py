"""Install the shared Mi-24 call-in fix in the Amiga code hunk."""
import copy
import struct
from src.build_common import ROOT, WORK, assembler, run_tool
from src.hunk_executable import read_hunks, serialize


def patch_game(game):
    run_tool([assembler(), '-m68000', '-Fhunkexe', '-nosym',
              '-L', WORK/'mi24.lst', '-o', WORK/'mi24.hunk', ROOT/'src/mi24.s'],
             'mi24_assembler.log')
    header, segments = read_hunks(game)
    before = copy.deepcopy(segments)
    _, patch = read_hunks((WORK/'mi24.hunk').read_bytes())
    assert [p['type'] for p in patch] == [1001, 1003]
    code = bytearray(segments[0]['data'])
    start = len(code)
    extension = bytearray(patch[0]['data'])
    entry = start + struct.unpack_from('>I', extension)[0]
    for target, offsets in patch[0]['reloc'].items():
        assert target in (0, 1)
        for offset in offsets:
            if target == 0:
                value = struct.unpack_from('>I', extension, offset)[0]
                struct.pack_into('>I', extension, offset, value+start)
            segments[0]['reloc'].setdefault(0, []).append(start+offset)
    off = 0x4138-0x9c
    expected = bytes.fromhex('0c730015406a664e')
    assert code[off:off+8] == expected
    assert not any(off <= r < off+8 for offsets in before[0]['reloc'].values() for r in offsets)
    code[off:off+8] = b'\x4e\xf9'+struct.pack('>I', entry)+b'\x4e\x71'
    segments[0]['reloc'].setdefault(0, []).append(off+2)
    code.extend(extension)
    segments[0]['data'] = bytes(code)
    segments[0]['size'] = header['hunks'][0]['size'] = len(code)
    result = serialize(header, segments)
    _, checked = read_hunks(result)
    assert checked[0]['data'] == bytes(code)
    assert checked[0]['reloc'] == {t:sorted(p) for t,p in segments[0]['reloc'].items()}
    for old, new in zip(before[1:], checked[1:]):
        assert old.get('data') == new.get('data') and old['size'] == new['size']
        assert {t:sorted(p) for t,p in old['reloc'].items()} == new['reloc']
    return result, dict(hook_file_offset='0x4138', added_code_bytes=len(extension),
                        extra_bss_bytes=0, mi24_call_in_accepted=True,
                        friendly_helicopter_commands_preserved=True,
                        enemy_does_not_emit_friendly_radio_text=True,
                        generation_and_arrival_timing_unchanged=True)
