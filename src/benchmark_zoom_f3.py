"""Count executed 68000 instructions and screen traffic in the added presentation.

This is a repeatable patch benchmark, not a measurement of whole-game FPS.
Camera/renderer hardware boundaries are stubbed, and asset loading is warmed up.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import test_zoom_f3 as t
from src.build_common import WORK
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MEM_WRITE
from unicorn.m68k_const import UC_M68K_REG_D0, UC_M68K_REG_D1, UC_M68K_REG_D2


def measure():
    u = t.machine()
    for address in (0x867e, 0xbf10):
        u.mem_write(t.old(address), b'\x4e\x75')
    t.w16(u, t.STATE + 0xbe, 3)
    t.w16(u, t.STATE + 0xc2, 3)
    t.w16(u, t.STATE + 0xc4, 0xffff)
    t.w16(u, t.STATE + 0xa6, 0x80)
    t.flag(u, 1)
    t.w16(u, t.BASE[33] + t.EX['hud_active'], 1)
    t.w16(u, t.STATE + 0x12, 82)
    t.w16(u, t.STATE + 0x14, 116)
    t.w16(u, t.STATE + 0x16, 15)
    u.mem_write(t.BASE[27] + 0x1d02c - 0x1b2f4, b'3058 *\0')
    counters = dict(instructions=0, screen_read_bytes=0, screen_write_bytes=0)
    def instruction(*args):
        counters['instructions'] += 1
    def memory(uc, access, address, size, value, user):
        counters['screen_write_bytes' if access == UC_MEM_WRITE else 'screen_read_bytes'] += size
    u.hook_add(UC_HOOK_CODE, instruction)
    u.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, memory,
               begin=t.SCREEN[0], end=t.SCREEN[0] + 31999)
    t.patch(u, 'render_begin', stop=t.old(0x8392))
    report = {}
    cases = [('frame_begin', dict(stop=t.old(0x828e))),
             ('render_begin', dict(stop=t.old(0x8392))),
             ('draw_sight', dict(regs={UC_M68K_REG_D0:126, UC_M68K_REG_D1:49, UC_M68K_REG_D2:0})),
             ('draw_range', {})]
    for name, arguments in cases:
        counters = dict(instructions=0, screen_read_bytes=0, screen_write_bytes=0)
        t.patch(u, name, **arguments)
        report[name] = counters
    report['total'] = {key: sum(row[key] for row in report.values()) for key in counters}
    report['scope'] = 'Steady-state added presentation only; no 3D renderer, original panels, disk IO or FPS timing'
    return report


if __name__ == '__main__':
    result = measure()
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else WORK / 'zoom_performance.json'
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
