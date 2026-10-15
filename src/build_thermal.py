"""Use the gunner's thermal material table for driver and commander optics."""
from src.hunk_executable import read_hunks


def patch_game(game):
    _, segments = read_hunks(game)
    # 0x66ac is called only by commander binoculars (0x86d6) and the
    # driver thermal switch (0x8774). Gunner thermal uses table 0 at 0x66a2.
    # Change the selected table, keeping the original switches and rendering.
    address = 0x66ac
    offset = segments[0]['data_file_offset'] + address - 0x9c
    assert game[offset:offset+10].hex() == '70014eb90000cccc4e75'
    result = bytearray(game)
    result[offset+1] = 0
    assert [i for i, (a, b) in enumerate(zip(game, result)) if a != b] == [offset+1]
    _, checked = read_hunks(bytes(result))
    assert [s['size'] for s in checked] == [s['size'] for s in segments]
    assert [s['reloc'] for s in checked] == [s['reloc'] for s in segments]
    return bytes(result), dict(
        original_file_offset=hex(address), before='7001', after='7000',
        previous_material_table=1, shared_gunner_material_table=0,
        changed_bytes=1, added_bytes=0, extra_instructions=0,
        affected_views=['commander binocular thermal', 'driver thermal'],
        material_tables_and_global_palette_unchanged=True,
        normal_views_and_thermal_switch_logic_unchanged=True)
