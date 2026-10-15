"""Execute original 68000 view selection and material lookup across sensors."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.build_common import SOURCE, WORK, write_json
from src.test_lead import (Game, game_from_adf, call, w16, r16, r32,
                           STATE, UNIT, OWN, old, glob)
from unicorn.m68k_const import *

REGS = [UC_M68K_REG_D0+i for i in range(8)] + [UC_M68K_REG_A0+i for i in range(8)]


def select(u, view, daylight, switches, binoculars):
    w16(u, STATE+0xa6, OWN)
    w16(u, STATE+0xbe, view)
    w16(u, STATE+0x50, daylight)
    for bit, offset in enumerate((0x4c, 0x4e, 0x50)):
        w16(u, UNIT+offset, (switches >> bit) & 1)
    w16(u, UNIT+0x2a, binoculars)
    # Stop immediately before camera projection: sensor selection has finished.
    call(u, 0x867e, stop=old(0x87fa if view < 4 else 0x8808))
    tables = [r32(u, glob(0x410d2)+4*i) for i in range(6)]
    mode = tables.index(r32(u, STATE+0x1e2))
    # The original state ends at 0x2c4; expanded material tables follow it.
    state = bytearray(u.mem_read(STATE, 0x2c4))
    state[0x1e2:0x1e6] = bytes(4)  # Pointer differs with appended color tables.
    return mode, bytes(state), [u.reg_read(r) for r in REGS]


def materials(u, count):
    pens = []
    for material in range(count):
        # Execute the same material-to-pen mapping used by polygons/horizon.
        call(u, 0xcd7a, stop=old(0x1e0c), regs={UC_M68K_REG_D0:material})
        pens.append(r16(u, STATE+0xc))
    return pens


def verify(original_blob, patched_blob):
    original, patched = Game(original_blob), Game(patched_blob)
    before, after = original.machine(), patched.machine()
    # Reuse each machine so transitions exercise replacement of a stale table.
    cases = thermal = normal = 0
    for daylight in (2, 3, 4, 5):
        for switches in range(8):
            for binoculars in (0, 1):
                for view in (0, 1, 2, 3, 4, 5):
                    a = select(before, view, daylight, switches, binoculars)
                    b = select(after, view, daylight, switches, binoculars)
                    gunner = view == 3 and switches & 2
                    other_sensor = ((view == 0 and binoculars and switches & 4)
                                    or (view == 2 and switches & 1))
                    assert a[0] == (0 if gunner else 1 if other_sensor else daylight)
                    assert b[0] == (0 if gunner or other_sensor else daylight)
                    assert a[1:] == b[1:], (view, daylight, switches, binoculars)
                    cases += 1
                    if gunner or other_sensor:
                        thermal += 1
                    else:
                        normal += 1

    # A freshly loaded gunner view in the unmodified game is the color reference.
    reference = original.machine()
    select(reference, 3, 2, 2, 0)
    expected = materials(reference, 35)
    expected += [expected[i] for i in (4, 6, 12, 4)]
    lookups = 0
    before_pens = {}
    for view, switches, binoculars, name in ((0, 4, 1, 'commander'),
                                            (2, 1, 0, 'driver'),
                                            (3, 2, 0, 'gunner')):
        u = patched.machine()
        select(u, view, 2, switches, binoculars)
        assert materials(u, 39) == expected, name
        lookups += 39
        old_u = original.machine()
        select(old_u, view, 2, switches, binoculars)
        before_pens[name] = materials(old_u, 35)
    assert before_pens['commander'] == before_pens['driver']
    assert before_pens['driver'] != before_pens['gunner']

    # Every normal material still matches the pre-fix game; enemy additions
    # keep their separately verified green/brown mapping from the color stage.
    for daylight in (2, 3, 4, 5):
        a, b = original.machine(), patched.machine()
        select(a, 2, daylight, 0, 0)
        select(b, 2, daylight, 0, 0)
        assert materials(a, 35) == materials(b, 35)
        lookups += 35
    return dict(all_passed=True, view_switch_cases=cases,
                thermal_cases=thermal, unchanged_normal_cases=normal,
                native_material_lookup_checks=lookups,
                thermal_materials_match_original_gunner=True,
                camera_viewport_and_other_state_unchanged=True,
                day_and_night_restoration_verified=True,
                original_different_sensor_pens=before_pens,
                unified_thermal_pens=expected, full_game_emulator_test=False)


if __name__ == '__main__':
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else WORK/'ZoomF3_test.adf'
    result = verify(game_from_adf(SOURCE.read_bytes()), game_from_adf(path.read_bytes()))
    write_json(WORK/'thermal_tests.json', result)
    print(f"Thermal colors verified: {result['view_switch_cases']} view/switch cases.")
