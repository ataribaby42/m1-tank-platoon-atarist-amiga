"""Regression for the external-view label left in Shift+F3's status row."""
from src import build_common  # Include the bundled instruction emulator.
from unicorn import UC_HOOK_CODE
from unicorn.m68k_const import UC_M68K_REG_D0, UC_M68K_REG_D2


def verify(u, state, screens, panel, status, status_end, erase, draw, message,
           call, w16, w32, planar):
    # Run the real panel hook and common status-list scheduler. Only the final
    # graphics primitives are stubbed: Amiga blitter drawing needs chipset
    # emulation. Verify that the native scheduler redraws messages on both
    # buffers after clearing, and still suppresses unchanged messages later.
    for address in (erase, draw): u.mem_write(address, b'\x4e\x75')
    draws = []
    u.hook_add(UC_HOOK_CODE,
        lambda uc, a, size, data: draws.append((int.from_bytes(uc.mem_read(state+8, 2), 'big'), uc.reg_read(UC_M68K_REG_D2))),
        begin=draw, end=draw)
    # The two stages share a boundary. Stop explicitly even if Unicorn has
    # already translated that boundary as part of the other stage.
    boundary = [status]
    u.hook_add(UC_HOOK_CODE,
        lambda uc, a, size, data: uc.emu_stop() if a == boundary[0] else None,
        begin=status, end=status_end)
    def execute(address, stop):
        boundary[0] = stop
        call(u, address, stop=stop)
    def tail(data):
        if planar: return b''.join(data[p*8000+7680:(p+1)*8000] for p in range(4))
        return data[30720:]
    def clear_tail(data):
        out = bytearray(data)
        if planar:
            for p in range(4): out[p*8000+7680:(p+1)*8000] = bytes(320)
        else: out[30720:] = bytes(1280)
        return bytes(out)
    originals = [bytes([0x55+i*0x55])*32000 for i in range(2)]
    for i in range(2): u.mem_write(screens[i], originals[i])
    w16(u, state+0xbe, 3); w16(u, state+0xa6, 0x80)
    w16(u, state+0xc4, 1)
    w32(u, message, 0x3036000)
    for i in range(2):
        w16(u, state+8, i)
        other = bytes(u.mem_read(screens[i^1], 32000))
        execute(panel, status)
        actual = bytes(u.mem_read(screens[i], 32000))
        assert not any(tail(actual)), 'External VIEW text survives the Shift+F3 panel refresh'
        assert actual == clear_tail(originals[i]), 'Status cleanup modified the cockpit'
        assert bytes(u.mem_read(screens[i^1], 32000)) == other
        assert u.reg_read(UC_M68K_REG_D0) == (1 if i == 0 else 0)
        before = len(draws)
        execute(status, status_end)
        assert draws[before:] == [(i, 0x3036000)], 'Current message was not redrawn after clearing'
    # A real message has now been drawn: keep representative nonzero status
    # pixels through subsequent frames, without repeatedly clearing the line.
    for i in range(2): u.mem_write(screens[i], originals[i])
    for i in (0, 1, 0, 1):
        w16(u, state+8, i)
        execute(panel, status)
        assert bytes(u.mem_read(screens[i], 32000)) == originals[i]
        before = len(draws)
        execute(status, status_end)
        assert len(draws) == before, 'Unchanged message lost its cached path'
    w32(u, message, 0x3036100)
    before = len(draws)
    # The native status list checks for changes on alternating frames.
    for i in (0, 1, 0, 1):
        w16(u, state+8, i)
        execute(panel, status)
        execute(status, status_end)
    assert sorted(draws[before:]) == [(0, 0x3036100), (1, 0x3036100)], ('New messages must reach both buffers', draws[before:])
    return dict(buffers_tested=2, stale_status_pixels_cleared=True,
                cockpit_and_other_buffer_preserved=True,
                current_message_redrawn_in_both_buffers=True,
                cached_status_preserved=True, new_messages_update_both_buffers=True)


def amiga():
    from src import test_zoom_f3 as t
    u = t.machine(); t.flag(u, 1)
    return verify(u, t.STATE, t.SCREEN, t.BASE[32]+t.EX['panel_begin'],
        t.old(0x8354), t.old(0x8380), t.old(0xa13c), t.old(0xa1a4),
        t.BASE[27]+0x3675a-0x1b2f4, t.call, t.w16, t.w32, True)


def st(game, ex):
    from src import test_st as t
    u = game.machine(); t.w16(u, t.BASE+ex['zoom_enabled'], 1)
    # Isolate the framebuffer/status transition from the software mouse cursor.
    # Its actual save/restore is covered by the isolated emulator check.
    u.mem_write(t.BASE+0xcc3e, b'\x4e\x75')
    return verify(u, t.STATE, [t.SCREEN, t.SCREEN+0x10000],
        t.BASE+ex['panel_begin'], t.BASE+0x794a, t.BASE+0x7976,
        t.BASE+0x97dc, t.BASE+0x9844, t.BASE+0x27f8e,
        lambda u, a, **kw: t.call(u, a-t.BASE, **kw), t.w16, t.w32, False)
