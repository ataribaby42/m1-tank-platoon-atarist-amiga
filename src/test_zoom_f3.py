"""Execute the installed 68000 patch with real planar buffers and game handlers."""
from pathlib import Path
import json
import random
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.build_zoom_f3 import read_hunks
from src.build_common import WORK
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_MEM_WRITE
from unicorn.m68k_const import *
from src.build_assets import RGB,asset,SPRITES

BASE=[0x1000000+i*0x40000 for i in range(34)]
STATE=BASE[27]+0x41400-0x1b2f4
STACK=0x400f000
RETURN=0x4000000
SCREEN=[0x3000000,0x3010000]
BITMAP=[0x3020000,0x3020040]
UNITS=0x3030000
UNIT=0x3034000
REPORT=json.loads((WORK/'zoom_f3_build.json').read_text())
EX=REPORT['exports']
REGS=[UC_M68K_REG_D0+i for i in range(8)]+[UC_M68K_REG_A0+i for i in range(7)]

def w16(u,a,n):u.mem_write(a,struct.pack('>H',n&65535))
def w32(u,a,n):u.mem_write(a,struct.pack('>I',n))
def r16(u,a):return struct.unpack('>H',u.mem_read(a,2))[0]

def machine():
    _,ss=read_hunks((WORK/'ZoomF3_game').read_bytes())
    u=Uc(UC_ARCH_M68K,UC_MODE_BIG_ENDIAN)
    u.ctl_set_cpu_model(UC_CPU_M68K_M68000)
    for i,s in enumerate(ss):
        u.mem_map(BASE[i],0x40000)
        b=bytearray(s.get('data',b''))
        for t,ofs in s['reloc'].items():
            for p in ofs:
                n=struct.unpack_from('>I',b,p)[0]
                struct.pack_into('>I',b,p,n+BASE[t])
        if b:u.mem_write(BASE[i],bytes(b))
    u.mem_map(0x3000000,0x40000)
    u.mem_map(RETURN,0x10000)
    u.mem_map(0xdff000,0x1000)
    for i in (0,1):
        w32(u,BASE[4]+0x14+i*4,BITMAP[i])
        u.mem_write(BITMAP[i],struct.pack('>HHBBH4I',40,200,0,4,0,
                    *[SCREEN[i]+p*8000 for p in range(4)]))
    for off in (0x80,0x100):w32(u,UNITS+off,UNIT)
    u.reg_write(UC_M68K_REG_SR,0x2000)
    u.reg_write(UC_M68K_REG_A2,STATE)
    u.reg_write(UC_M68K_REG_A3,UNITS)
    return u

def call(u,start,stop=RETURN,regs=None):
    for reg,value in (regs or {}).items():u.reg_write(reg,value)
    u.reg_write(UC_M68K_REG_A7,STACK)
    w32(u,STACK,RETURN)
    try:u.emu_start(start,stop,count=1500000)
    except Exception as e:raise RuntimeError(f'68000 exception PC={u.reg_read(UC_M68K_REG_PC):08x}') from e
    assert u.reg_read(UC_M68K_REG_PC)==stop,hex(u.reg_read(UC_M68K_REG_PC))

def patch(u,name,**kw):call(u,BASE[32]+EX[name],**kw)
def old(a):return BASE[0]+a-0x9c
def flag(u,value):w16(u,BASE[33]+EX['zoom_enabled'],value)

def main():
    results=[]
    u=machine();rng=random.Random(0xF3)
    # Renderer/camera calls themselves use Amiga hardware. Exercise our boundary
    # with deterministic frame content here; the real pipeline is tested in UAE.
    for a in (0x867e,0xbf10):u.mem_write(old(a),b'\x4e\x75')
    originals=[rng.randbytes(32000) for _ in range(2)]
    for i,b in enumerate(originals):u.mem_write(SCREEN[i],b)
    w16(u,STATE+0xbe,3);w16(u,STATE+0xa6,0x80);flag(u,1)
    w16(u,STATE+0xc2,3);w16(u,STATE+0xc4,0xffff)
    screen_writes=[]
    # Install before executing code: Unicorn can retain translated blocks.
    hook=u.hook_add(UC_HOOK_MEM_WRITE,lambda uc,a,addr,size,value,data: screen_writes.append((addr,size)),
                   begin=SCREEN[0],end=SCREEN[1]+31999)
    def expected_cockpit(original,on=0):
        result=bytearray(original)
        result[:7680]=bytes(7680)
        for p in range(1,4):result[p*8000:p*8000+7680]=bytes(7680)
        def paste(name,x0,y0):
            size=(320,200) if name=='kokpit' else (26,20) if 'prepinac' in name else (26,12)
            im=asset(name,size).convert('RGBA')
            for y in range(im.height):
                for x in range(im.width):
                    dx=x0+x;dy=y0+y;c=im.getpixel((x,y))
                    if not c[3] or not (0<=dx<320 and 0<=dy<192):continue
                    color=RGB.index(c[:3]);mask=1<<(7-dx%8)
                    for p in range(4):
                        pos=p*8000+dy*40+dx//8
                        result[pos]=(result[pos]&~mask)|(mask if color&(1<<p) else 0)
        paste('kokpit',0,0);paste('smoke1_prepinac_'+str(on),309,34);paste('smoke1_svetlo_'+str(on),312,13)
        return bytes(result)
    for index in (0,1):
        w16(u,STATE+8,index)
        regs={r:u.reg_read(r) for r in REGS}
        patch(u,'render_begin',stop=old(0x8392))
        assert bytes(u.mem_read(SCREEN[index],32000))==expected_cockpit(originals[index]),'PNG cockpit mismatch'
        assert {r:u.reg_read(r) for r in REGS}==regs,'Presentation hook changed registers'
        assert [r16(u,STATE+o) for o in (0x1fc,0x204,0x200,0x208,0x20a,0x20c)]==[64,10,257,187,160,98]
    raw=(WORK/'zoom_art_raw.bin').read_bytes()
    assert bytes(u.mem_read(BASE[33]+EX['art_raw'],len(raw)))==raw
    results.append('Both frame buffers use the actual editable PNG cockpit and Smoke 1 assets; status rows unchanged')
    results.append('68000 asset decompression reproduces the compiled PNG data exactly')
    for smoke in (0,1,1,0):
        w16(u,UNIT+0x48,smoke)
        for index in (0,1):
            w16(u,STATE+8,index)
            patch(u,'frame_begin',stop=old(0x828e))
            patch(u,'panel_begin',stop=old(0x8354))
            patch(u,'render_begin',stop=old(0x8392))
            assert bytes(u.mem_read(SCREEN[index],32000))==expected_cockpit(originals[index],smoke)
            screen_writes.clear()
            patch(u,'frame_begin',stop=old(0x828e))
            patch(u,'panel_begin',stop=old(0x8354))
            patch(u,'render_begin',stop=old(0x8392))
            assert not screen_writes,'Unchanged cockpit/Smoke was drawn again'
    # A requested redraw (for example another selected tank) must finish,
    # rather than resetting the two-frame refresh counter on every frame.
    w16(u,STATE+0xc4,1)
    for index in (0,1,0,1):
        w16(u,STATE+8,index)
        patch(u,'frame_begin',stop=old(0x828e))
        patch(u,'panel_begin',stop=old(0x8354))
        patch(u,'render_begin',stop=old(0x8392))
    assert r16(u,STATE+0xc4)==0xffff
    screen_writes.clear()
    patch(u,'frame_begin',stop=old(0x828e))
    patch(u,'panel_begin',stop=old(0x8354))
    patch(u,'render_begin',stop=old(0x8392))
    assert not screen_writes,'Requested refresh never returned to the cached path'
    u.hook_del(hook)
    results.append('Each buffer caches its cockpit and Smoke state: no pixel writes until Smoke or the view changes')
    flag(u,0)
    for index in (0,1):
        w16(u,STATE+8,index)
        patch(u,'frame_begin',stop=old(0x828e))
        assert bytes(u.mem_read(SCREEN[index],32000))==originals[index]
        assert r16(u,STATE+0xc4)==1,'Returning to F3 must refresh original instruments'
    results.append('Both screen buffers restore without pixel loss or accumulation')
    for zoom,view in ((0,3),(1,0),(1,1),(1,2),(1,4),(1,5)):
        flag(u,zoom);w16(u,STATE+0xbe,view)
        for refresh in (0xffff,0,1):
            w16(u,STATE+0xc4,refresh)
            patch(u,'panel_begin',stop=old(0x8322 if refresh==0xffff else 0x8314))
            assert r16(u,STATE+0xc4)==(0xffff if refresh==0xffff else (refresh-1)&65535)
    results.append('Original panel refresh logic is unchanged outside Shift+F3')
    for view in (0,1,2,4,5):
        w16(u,STATE+0xbe,view)
        patch(u,'frame_end',stop=old(0x5de4))
        assert bytes(u.mem_read(SCREEN[1],32000))==originals[1]
    flag(u,0);w16(u,STATE+0xbe,3)
    patch(u,'frame_end',stop=old(0x5de4))
    assert bytes(u.mem_read(SCREEN[1],32000))==originals[1]
    results.append('Normal F3 and all other views bypass scaling')

    u=machine()
    for enabled in (0,1):
        w16(u,BASE[33]+EX['native_scene'],enabled)
        for x,z,shift in [(-25,167,9),(25,167,9),(-1,13,11),(0,100,9),(127,489,9),(9,53,11)]:
            patch(u,'project_axis',regs={UC_M68K_REG_D0:x&65535,UC_M68K_REG_D2:z,UC_M68K_REG_D3:shift})
            expected=int(int((x<<shift)*(8/5 if enabled else 1))/z)
            assert u.reg_read(UC_M68K_REG_D0)&65535==expected&65535
    results.append('Native 3D perspective scales before division, preserving field of view and fractional detail')
    patch(u,'unpack_art')
    w16(u,BASE[33]+EX['hud_active'],1)
    w16(u,STATE+0x12,82);w16(u,STATE+0x14,116);w16(u,STATE+0x16,15)
    u.mem_write(BASE[27]+0x1d02c-0x1b2f4,b'3058 *\0')
    patch(u,'draw_range')
    assert any(u.mem_read(SCREEN[0]+132*40,12*40)),'Enlarged distance font not drawn'
    patch(u,'draw_sight',regs={UC_M68K_REG_D0:126,UC_M68K_REG_D1:49,UC_M68K_REG_D2:0})
    assert any(u.mem_read(SCREEN[0]+79*40,38*40)),'Enlarged reticle not drawn'
    results.append('New reticle, distance digits and star PNGs draw directly at native pixel positions')
    verify_sprite_pixels()
    results.append('Planar HUD matches PNG pixels at every bit alignment, with tint, transparency and edge clipping')

    u=machine();w16(u,STATE+0xbe,3)
    for off,n in ((0xa2,0x80),(0xa6,0x80),(0xa8,0x100),(0xd8,17),(0xda,11),(0xac,1),(0xb8,3058)):
        w16(u,STATE+off,n)
    previous=bytes(u.mem_read(STATE,0x2ac))
    patch(u,'key_handler',regs={UC_M68K_REG_D0:0xfd})
    assert bytes(u.mem_read(STATE,0x2ac))==previous
    assert r16(u,BASE[33])==1 and u.reg_read(UC_M68K_REG_SR)&1
    results.append('Shift+F3 from F3 preserves every game-state byte, including target and aim')
    for view in (0,1,2,4,5):
        a=machine();b=machine()
        for inst in (a,b):
            w16(inst,STATE+0xbe,view);w16(inst,STATE+0xa6,0x80);w16(inst,STATE+0xa8,0x100)
            w16(inst,UNIT+0x7c,1)
        call(a,old(0x9024),regs={UC_M68K_REG_D0:0xf3})
        patch(b,'key_handler',regs={UC_M68K_REG_D0:0xfd})
        assert bytes(a.mem_read(STATE,0x2ac))==bytes(b.mem_read(STATE,0x2ac))
        assert r16(b,STATE+0xbe)==3 and r16(b,BASE[33])==1
    results.append('Shift+F3 from each other view produces the same game state as original F3')
    u=machine();w16(u,STATE+0xbe,3)
    for off,n in ((0xa2,0x80),(0xa6,0x80),(0xa8,0x100),(0xd8,17),(0xda,11),(0xac,1),(0xb8,3058)):
        w16(u,STATE+off,n)
    w16(u,UNIT+0x7c,1)
    previous=bytes(u.mem_read(STATE,0x2ac));previous_unit=bytes(u.mem_read(UNIT,0x100))
    for repeat in range(3):
        for key,zoom in ((0xfd,1),(0xf3,0)):
            patch(u,'key_handler',regs={UC_M68K_REG_D0:key})
            assert bytes(u.mem_read(STATE,0x2ac))==previous,('View toggle changed target or aim',hex(key),repeat)
            assert bytes(u.mem_read(UNIT,0x100))==previous_unit,'View toggle changed unit state'
            assert r16(u,BASE[33])==zoom and u.reg_read(UC_M68K_REG_SR)&1
    results.append('Repeated F3 <-> Shift+F3 preserves all game and unit state, including target and aim in both directions')
    # Ordinary F3 still enters the gunner normally, including when zoom was
    # left active by switching to a different view before pressing F3.
    for view in (0,1,2,3,4,5):
        for zoom in ((0,) if view==3 else (0,1)):
            a=machine();b=machine();flag(b,zoom)
            for inst in (a,b):
                w16(inst,STATE+0xbe,view);w16(inst,STATE+0xa6,0x80);w16(inst,STATE+0xa8,0x100)
                w16(inst,STATE+0xd8,17);w16(inst,STATE+0xda,11);w16(inst,UNIT+0x7c,1)
            call(a,old(0x9024),regs={UC_M68K_REG_D0:0xf3})
            patch(b,'key_handler',regs={UC_M68K_REG_D0:0xf3})
            assert bytes(a.mem_read(STATE,0x2ac))==bytes(b.mem_read(STATE,0x2ac)),(view,zoom)
            assert bytes(a.mem_read(UNIT,0x100))==bytes(b.mem_read(UNIT,0x100))
            assert r16(b,BASE[33])==0
    results.append('F3 outside the enlarged gunner view retains the original F3 behavior')

    u=machine();flag(u,1);w16(u,STATE+0xbe,3)
    latch=BASE[27]+0x39bcc-0x1b2f4
    for x,y,button,expected in [(312,40,2,8),(303,40,2,0),(319,56,2,8),(320,40,2,0),
                               (312,28,2,0),(312,57,2,0),(312,40,0,0),(312,40,1,0),
                               (156,61,2,0),(260,90,2,0),(120,170,2,0)]:
        w16(u,STATE+0x26,x);w16(u,STATE+0x28,y);w16(u,STATE+0x2a,button)
        w16(u,STATE+0x16e,0);w16(u,latch,0)
        patch(u,'click_handler')
        assert r16(u,STATE+0x16e)==expected,(x,y,button)
        assert r16(u,latch)==expected
    w16(u,STATE+0x26,312);w16(u,STATE+0x28,40);w16(u,STATE+0x2a,2)
    w16(u,STATE+0x16e,0);w16(u,latch,8)
    patch(u,'click_handler');assert r16(u,STATE+0x16e)==0
    results.append('Only Smoke 1 accepts a left click; its latch prevents repeat firing while held')
    flag(u,0)
    patch(u,'click_handler',stop=old(0x8610))
    assert u.reg_read(UC_M68K_REG_D0)&65535==3
    flag(u,1);before=bytes(u.mem_read(STATE,0x2ac));patch(u,'sliders')
    assert bytes(u.mem_read(STATE,0x2ac))==before
    results.append('Original click handling remains available in ordinary views; hidden sliders are disabled')
    patch(u,'reset_view',stop=old(0x824a))
    assert r16(u,BASE[33])==0 and r16(u,BASE[33]+2)==0
    results.append('Starting/resetting a mission clears zoom and saved-buffer state')
    verify_laser_acquisition()
    results.append('Installed laser hook rejects invalid distances in F3 and Shift+F3 without acquiring a target or changing aim/ballistics')
    results.append('Valid laser acquisition (200..7998 m), missing targets and existing-lock failure handling match the original game')
    report=dict(cpu='Motorola 68000',checks=results,all_passed=True)
    (WORK/'zoom_f3_tests.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

def verify_laser_acquisition():
    original=machine();fixed=machine()
    original.mem_write(old(0x323a),bytes.fromhex('302a023c6a08'))
    installed=bytes(fixed.mem_read(old(0x323a),6))
    assert installed==b'\x4e\xf9'+struct.pack('>I',BASE[32]+EX['laser_acquire'])
    initial=bytes(fixed.mem_read(BASE[27],0x40000))
    lock=BASE[27]+0x1d0d4-0x1b2f4
    registers={r:0x13570000+i for i,r in enumerate(REGS)}
    registers.update({UC_M68K_REG_A2:STATE,UC_M68K_REG_A3:UNITS,UC_M68K_REG_A5:UNIT})
    for zoom in (0,1):
        for distance in (0,3,199,200,3999,4000,7998,7999,16383,65535):
            for target in (0x100,0xffff):
                for already_locked in (0,1):
                    case=(zoom,distance,target,already_locked)
                    for u in (original,fixed):
                        u.mem_write(BASE[27],initial);flag(u,zoom)
                        for off,value in ((0xbe,3),(0xb8,distance),(0x23c,target),
                                          (0xac,0 if already_locked else 1),(0xd8,17),(0xda,11)):
                            w16(u,STATE+off,value)
                        for off,value in ((0xe,22528),(0x2e,0xfe6b),(0x20,12344),(0x22,3086)):
                            w16(u,UNIT+off,value)
                        for off,value in ((0,already_locked),(2,0x580 if already_locked else 0xffff),
                                          (4,123),(6,456)):
                            w16(u,lock+off,value)
                        u.reg_write(UC_M68K_REG_SR,0x2000)
                    unit_before=bytes(fixed.mem_read(UNIT,0x100))
                    valid=200<=distance<7999
                    # Compare successful/missing-target paths with original code.
                    # Invalid positive IDs must take the original failure path,
                    # preserving its existing-lock semantics as well as registers.
                    reference_registers=registers.copy()
                    reference_start=old(0x323a)
                    if not valid and target!=0xffff:
                        reference_start=old(0x3240)
                        reference_registers[UC_M68K_REG_D0]=(registers[UC_M68K_REG_D0]&0xffff0000)|target
                    call(original,reference_start,stop=old(0x3276),regs=reference_registers)
                    call(fixed,old(0x323a),stop=old(0x3276),regs=registers)
                    assert bytes(fixed.mem_read(BASE[27],0x40000))==bytes(original.mem_read(BASE[27],0x40000)),case
                    assert [fixed.reg_read(r) for r in REGS+[UC_M68K_REG_SR]]==[
                        original.reg_read(r) for r in REGS+[UC_M68K_REG_SR]],case
                    assert bytes(fixed.mem_read(UNIT,0x100))==unit_before,case
                    if valid and target!=0xffff:
                        assert r16(fixed,lock)==1 and r16(fixed,lock+2)==target,case
                        assert r16(fixed,STATE+0xac)==0,case
                    else:
                        assert r16(fixed,lock)==already_locked,case
                        assert r16(fixed,STATE+0xac)==1,case
                        assert (r16(fixed,STATE+0xd8),r16(fixed,STATE+0xda))==(17,11),case

def verify_sprite_pixels():
    u=machine();patch(u,'unpack_art')
    manifest=REPORT['asset_manifest']
    background=random.Random(68000).randbytes(32000)
    # draw_range sets the pen tint, including nonwhite colored pixels in PNGs.
    tint_address=BASE[33]+EX['hud_active']+2
    for name,size in SPRITES:
        im=asset(name,size)
        opaque=[(x,y,im.getpixel((x,y))) for y in range(size[1]) for x in range(size[0])
                if im.getpixel((x,y))<16]
        for tint in (-1,12,2):
            w16(u,tint_address,tint)
            for index,x0,y0 in [(i%2,96+i,79) for i in range(16)]+[(0,-3,-2),(1,309,34),(0,312,13),(1,315,189)]:
                expected=bytearray(background)
                for x,y,color in opaque:
                    x+=x0;y+=y0
                    if not (0<=x<320 and 0<=y<192):continue
                    if color==15 and tint>=0:color=tint
                    mask=128>>(x%8)
                    for plane in range(4):
                        pos=plane*8000+y*40+x//8
                        expected[pos]=(expected[pos]&~mask)|(mask if color&(1<<plane) else 0)
                u.mem_write(SCREEN[index],background);w16(u,STATE+8,index)
                registers={UC_M68K_REG_A0:BASE[33]+EX['art_raw']+manifest['offsets'][name.upper()],
                           UC_M68K_REG_D0:x0&65535,UC_M68K_REG_D1:y0&65535}
                patch(u,'draw_art',regs=registers)
                assert bytes(u.mem_read(SCREEN[index],32000))==expected,(name,tint,index,x0,y0)
                assert all(u.reg_read(r)==v for r,v in registers.items())


if __name__=='__main__':main()
