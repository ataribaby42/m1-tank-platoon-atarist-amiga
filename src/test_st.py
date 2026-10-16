"""Execute the ST binary's real 68000 fixes and native sprite renderer."""
from pathlib import Path
import contextlib
import json
import random
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.build_common import ROOT
from src.st_addresses import CODE, DATA, STATE as STATE_OFFSET, SCREENS
from src.st_executable import TOSExecutable
from src.build_st_assets import ST_WORK
from src import test_lead as lead
from src.test_lead import w16,w32,r16,r32,UNITS,UNIT,OWN,RETURN,STACK
from unicorn import Uc,UC_ARCH_M68K,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
from unicorn.m68k_const import *

BASE=0x1000000
STATE=BASE+STATE_OFFSET
SCREEN=0x5000000
TEST_CODE={**CODE,0x361e:0x2be6,0x36c2:0x2c8a,0x5e2c:0x53fa,
           0x5730:0x4cfc,0x584c:0x4e18,0x5838:0x4e04,0x623c:0x580a,
           0xcf04:0xc5d6,0x87fa:0x7e1e,0x8808:0x7e2c,0xcd7a:0xc448}


class Game:
    def __init__(self,blob): self.exe=TOSExecutable(blob)
    def machine(self,cpu_model=UC_CPU_M68K_M68000,supervisor=True):
        u=Uc(UC_ARCH_M68K,UC_MODE_BIG_ENDIAN);u.ctl_set_cpu_model(cpu_model)
        u.mem_map(BASE,0x100000)
        u.mem_write(BASE,self.exe.relocated(BASE))
        u.mem_map(UNITS,0x10000);u.mem_map(RETURN,0x10000);u.mem_map(SCREEN,0x20000)
        u.reg_write(UC_M68K_REG_SR,0x2000 if supervisor else 0)
        u.reg_write(UC_M68K_REG_A2,STATE);u.reg_write(UC_M68K_REG_A3,UNITS)
        w32(u,UNITS+OWN,UNIT);w16(u,STATE+0x3c,1)
        for record in range(0,0x1800,0x80):w16(u,UNITS+record+4,0xffff)
        w16(u,UNITS+OWN+4,0);w16(u,UNITS+lead.TARGET+4,0)
        for i in range(2):w32(u,BASE+SCREENS+4*i,SCREEN+0x10000*i)
        return u


def call(u,address,stop=RETURN,regs=None):
    for r,v in (regs or {}).items():u.reg_write(r,v&0xffffffff)
    u.reg_write(UC_M68K_REG_A7,STACK);w32(u,STACK,RETURN)
    try:u.emu_start(BASE+address,stop,count=2000000)
    except Exception as e:raise RuntimeError(f'ST 68000 PC={u.reg_read(UC_M68K_REG_PC)-BASE:x}') from e
    assert u.reg_read(UC_M68K_REG_PC)==stop,hex(u.reg_read(UC_M68K_REG_PC))


@contextlib.contextmanager
def shared_lead_tests():
    replacements=dict(Game=Game,STATE=STATE,old=lambda a:BASE+TEST_CODE[a],glob=lambda a:BASE+DATA[a])
    saved={n:getattr(lead,n) for n in replacements}
    for n,v in replacements.items():setattr(lead,n,v)
    try:yield
    finally:
        for n,v in saved.items():setattr(lead,n,v)


def encode(pixels):
    b=bytearray(32000)
    for y in range(200):
        for x in range(320):
            n=pixels[y*320+x]
            for p in range(4):
                if n&(1<<p): b[y*160+(x//16)*8+p*2+(x%16)//8]|=128>>(x%8)
    return bytes(b)


def sprite_tests(game,exports):
    raw=(ST_WORK/'zoom_art_raw.bin').read_bytes()
    manifest=json.loads((ST_WORK/'zoom_art_manifest.json').read_text())
    u=game.machine();call(u,exports['unpack_art'])
    assert bytes(u.mem_read(BASE+exports['art_raw'],len(raw)))==raw
    # Tint word follows hud_active in the maintained shared BSS layout.
    tint_addr=BASE+exports['hud_active']+2
    rng=random.Random(68000)
    pixels=bytes(rng.randrange(16) for _ in range(64000)); background=encode(pixels)
    cases=0
    for name, size in manifest['sprites'].items():
        offset=manifest['offsets'][name.upper()]; width,height=size
        sprite=raw[offset+4:offset+4+width*height]
        for x,y in [(96+i,132) for i in range(16)]+[(-3,1),(310,10),(0,188),(-4,-3)]:
            for tint in (-1,2):
                u.mem_write(SCREEN,background);u.mem_write(SCREEN+0x10000,background)
                w16(u,STATE+8,cases&1);w16(u,tint_addr,tint)
                expected=bytearray(pixels)
                for sy in range(height):
                    for sx in range(width):
                        c=sprite[sy*width+sx];xx,yy=x+sx,y+sy
                        if c==16 or not(0<=xx<320 and 0<=yy<192):continue
                        expected[yy*320+xx]=tint if c==15 and tint>=0 else c
                call(u,exports['draw_art'],regs={UC_M68K_REG_D0:x,UC_M68K_REG_D1:y,
                                                 UC_M68K_REG_A0:BASE+exports['art_raw']+offset})
                assert bytes(u.mem_read(SCREEN+0x10000*(cases&1),32000))==encode(expected),(name,x,y,tint)
                assert bytes(u.mem_read(SCREEN+0x10000*((cases&1)^1),32000))==background
                cases+=1
    return dict(sprite_cases=cases,all_pixels_match_reference=True,status_rows_preserved=True,
                double_buffer_selection=True,unpack_matches_asset_compiler=True)


def control_tests(game,ex):
    cases=0
    for view in (0,1,2,3,4,5):
        for key in (0xfd,0xf3):
            for zoom in (0,1):
                u=game.machine();w16(u,STATE+0xbe,view);w16(u,BASE+ex['zoom_enabled'],zoom)
                w16(u,UNITS+OWN+8,0x580);w16(u,BASE+0xe95a,1);w16(u,BASE+0xe95c,0x580)
                consumed=view==3 and (key==0xfd or (key==0xf3 and zoom))
                stop=RETURN if consumed else BASE+(0x86ac if key==0xfd else 0x8678)
                call(u,ex['key_handler'],stop=stop,regs={UC_M68K_REG_D0:key})
                assert r16(u,UNITS+OWN+8)==0x580 and r16(u,BASE+0xe95c)==0x580
                assert r16(u,BASE+ex['zoom_enabled'])==(1 if key==0xfd else 0)
                cases+=1
    laser=0
    for target in (-1,0,0x580):
        for distance in (0,199,200,3999,4000,7998,7999,65535):
            u=game.machine();w16(u,STATE+0x23c,target);w16(u,STATE+0xb8,distance)
            valid=target>=0 and 200<=distance<7999
            call(u,ex['laser_acquire'],stop=BASE+(0x27d8 if valid else 0x27d0))
            laser+=1
    smoke=0
    for x,y in ((303,40),(304,28),(304,29),(319,56),(320,40),(312,57),(150,80)):
        u=game.machine();w16(u,STATE+0xbe,3);w16(u,BASE+ex['zoom_enabled'],1)
        w16(u,STATE+0x26,x);w16(u,STATE+0x28,y);w16(u,STATE+0x2a,2)
        call(u,ex['click_handler'])
        assert r16(u,STATE+0x16e)==(8 if 304<=x<320 and 29<=y<57 else 0)
        smoke+=1
    return dict(key_cases=cases,laser_cases=laser,smoke_hitbox_cases=smoke)


def cache_tests(game,ex):
    u=game.machine()
    # Isolate native presentation from the original camera/scene in this test.
    # Full unmodified setup and scene paths are exercised in emulator testing.
    u.mem_write(BASE+0x7c9e,b'\x4e\x75')
    w16(u,STATE+0xa6,OWN);w16(u,STATE+0xbe,3);w16(u,STATE+0xc2,3)
    w16(u,STATE+0xc4,-1);w16(u,BASE+ex['zoom_enabled'],1)
    initial=[bytes([0x55+i])*32000 for i in range(2)]
    for i in range(2):
        u.mem_write(SCREEN+0x10000*i,initial[i]);w16(u,STATE+8,i)
        call(u,ex['render_begin'],stop=BASE+0xb5dc)
        assert bytes(u.mem_read(BASE+ex[f'backup{i}'],30720))==initial[i][:30720]
        assert bytes(u.mem_read(SCREEN+0x10000*i+30720,1280))==initial[i][30720:]
        assert [r16(u,STATE+o) for o in (0x1fc,0x204,0x200,0x208)]==[64,10,257,187]
        # A rendered scene must survive a second frame with unchanged Smoke.
        u.mem_write(SCREEN+0x10000*i+80*160+10*8,b'\xaa'*8)
        before=bytes(u.mem_read(SCREEN+0x10000*i,32000))
        call(u,ex['frame_begin'],stop=BASE+0x786c)
        call(u,ex['render_begin'],stop=BASE+0xb5dc)
        assert bytes(u.mem_read(SCREEN+0x10000*i,32000))==before
        w16(u,UNIT+0x48,1)
        call(u,ex['render_begin'],stop=BASE+0xb5dc)
        after=bytes(u.mem_read(SCREEN+0x10000*i,32000))
        changed=[n for n,(a,b) in enumerate(zip(before,after)) if a!=b]
        assert changed and all(13<=n//160<=53 and n%160>=152 for n in changed)
        w16(u,UNIT+0x48,0)
    w16(u,BASE+ex['zoom_enabled'],0)
    for i in range(2):
        w16(u,STATE+8,i);call(u,ex['frame_begin'],stop=BASE+0x786c)
        assert bytes(u.mem_read(SCREEN+0x10000*i,32000))==initial[i]
    return dict(buffers_tested=2,cockpit_not_repainted_each_frame=True,
                smoke_changes_are_local=True,original_screens_restored=True,status_preserved=True)


def clipping_tests(original,patched):
    rng=random.Random(68000);cases=0
    for cpu in (UC_CPU_M68K_M68000,UC_CPU_M68K_M68020):
        pair=[g.machine(cpu_model=cpu,supervisor=False) for g in (original,patched)]
        for viewport in ((96,6,216,116),(64,10,257,187),(0,0,319,191)):
            for i in range(220):
                scale=120000 if i>=200 else 900
                points=[rng.randrange(-scale,scale) for _ in range(4)]
                records=[]
                for u in pair:
                    edge=SCREEN+0x8000
                    u.mem_write(edge,bytes(16))
                    regs=dict(zip((UC_M68K_REG_D2,UC_M68K_REG_D3,UC_M68K_REG_D4,UC_M68K_REG_D5),points))
                    regs.update(dict(zip((UC_M68K_REG_A0,UC_M68K_REG_A1,UC_M68K_REG_A5,UC_M68K_REG_A6),viewport)))
                    regs[UC_M68K_REG_A4]=edge
                    call(u,0xc5d6,regs=regs)
                    words=struct.unpack('>8H',u.mem_read(edge,16))
                    records.append([words[i] for i in (0,1,3,5,7)])
                assert records[0]==records[1],(points,records)
                cases+=1
    return dict(original_clipper_results_preserved=cases)


def thermal_tests(original,patched):
    cases=0
    for daylight in (2,3,4,5):
        for switches in range(8):
            for binoculars in (0,1):
                for view in range(6):
                    states=[]
                    thermal=(view==3 and switches&2) or (view==2 and switches&1) or (view==0 and binoculars and switches&4)
                    for game in (original,patched):
                        u=game.machine();w16(u,STATE+0xa6,OWN);w16(u,STATE+0xbe,view)
                        w16(u,STATE+0x50,daylight);w16(u,UNIT+0x2a,binoculars)
                        for bit,offset in enumerate((0x4c,0x4e,0x50)):w16(u,UNIT+offset,(switches>>bit)&1)
                        call(u,0x7c9e,stop=BASE+(0x7e1e if view<4 else 0x7e2c))
                        table=r32(u,STATE+0x1e2)
                        mode=[r32(u,BASE+0x3297c+i*4) for i in range(6)].index(table)
                        expected=(0 if view==3 else 1) if thermal else daylight
                        if game is patched and thermal:expected=0
                        assert mode==expected,(view,switches,daylight,mode)
                        state=bytearray(u.mem_read(STATE,0x2c4));state[0x1e2:0x1e6]=bytes(4)
                        states.append(state)
                    assert states[0]==states[1]
                    cases+=1
    return dict(view_switch_cases=cases,all_thermal_views_match_gunner=True,camera_state_unchanged=True)


def verify(original_blob,patched_blob,report):
    original,patched=Game(original_blob),Game(patched_blob)
    print('ST native sprite and control tests...')
    result=dict(graphics=sprite_tests(patched,report['exports']),controls=control_tests(patched,report['exports']))
    result['cache']=cache_tests(patched,report['exports'])
    from src.test_zoom_status import st as verify_status
    result['status_refresh']=verify_status(patched,report['exports'])
    result['clipping']=clipping_tests(original,patched)
    result['thermal']=thermal_tests(original,patched)
    print('ST stationary/moving/turning/low-FPS fire-control tests...')
    with shared_lead_tests():result['lead']=lead.verify(original_blob,patched_blob)
    from src.test_mi24 import verify as verify_mi24
    result['mi24']=verify_mi24(original_blob,patched_blob,'st')
    result['all_passed']=True
    return result


if __name__=='__main__':
    from src.build_st import SOURCE
    from src.st_disk import STDisk
    report=json.loads((ST_WORK/'build.json').read_text())
    result=verify(STDisk(SOURCE.read_bytes()).read('GAME.PRG'),(ST_WORK/'GAME.PRG').read_bytes(),report)
    from src.build_common import write_json
    write_json(ST_WORK/'tests.json',result)
    print('All ST processor checks passed.')
