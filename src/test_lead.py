"""Execute real tracking, launch, allocation and flight instructions on a 68000.

Uses only executable hunks from original/build ADFs; no emulator snapshots.
Horizontal closest approach excludes random dispersion and terrain collisions.
"""
from pathlib import Path
import math
import statistics
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.build_common import SOURCE, WORK, write_json
from src.hunk_executable import read_hunks
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.m68k_const import *

BASE = [0x1000000+i*0x40000 for i in range(34)]
STATE = BASE[27]+0x41400-0x1b2f4
UNITS, UNIT, RETURN, STACK = 0x3030000, 0x3034000, 0x4000000, 0x400f000
OWN, TARGET = 0x80, 0x580


def word(n): return (n+32768)%65536-32768
def w16(u,a,n): u.mem_write(a,struct.pack('>H',n&65535))
def w32(u,a,n): u.mem_write(a,struct.pack('>I',n&0xffffffff))
def r16(u,a): return struct.unpack('>H',u.mem_read(a,2))[0]
def r32(u,a): return struct.unpack('>i',u.mem_read(a,4))[0]
def old(a): return BASE[0]+a-0x9c
def glob(a): return BASE[27]+a-0x1b2f4


class Game:
    def __init__(self, blob):
        _, self.segments = read_hunks(blob)

    def machine(self, cpu_model=UC_CPU_M68K_M68000, supervisor=True):
        u=Uc(UC_ARCH_M68K,UC_MODE_BIG_ENDIAN)
        u.ctl_set_cpu_model(cpu_model)
        for i,s in enumerate(self.segments):
            assert s['size']<=0x40000
            u.mem_map(BASE[i],0x40000)
            b=bytearray(s.get('data',b''))
            for target, offsets in s['reloc'].items():
                for offset in offsets:
                    value=struct.unpack_from('>I',b,offset)[0]
                    struct.pack_into('>I',b,offset,value+BASE[target])
            if b:u.mem_write(BASE[i],bytes(b))
        u.mem_map(UNITS,0x10000);u.mem_map(RETURN,0x10000)
        u.reg_write(UC_M68K_REG_SR,0x2000 if supervisor else 0)
        u.reg_write(UC_M68K_REG_A2,STATE);u.reg_write(UC_M68K_REG_A3,UNITS)
        w32(u,UNITS+OWN,UNIT)
        w16(u,STATE+0x3c,1)  # Sound disabled; original sound logic still executes.
        for record in range(0,0x1800,0x80):w16(u,UNITS+record+4,0xffff)
        w16(u,UNITS+OWN+4,0);w16(u,UNITS+TARGET+4,0)
        return u


def call(u,address,stop=RETURN,regs=None):
    for r,v in (regs or {}).items():u.reg_write(r,v)
    u.reg_write(UC_M68K_REG_A7,STACK);w32(u,STACK,RETURN)
    try:u.emu_start(old(address),stop,count=1000000)
    except Exception as e:raise RuntimeError(f'68000 PC={u.reg_read(UC_M68K_REG_PC):x}') from e
    assert u.reg_read(UC_M68K_REG_PC)==stop,hex(u.reg_read(UC_M68K_REG_PC))


def shot(game,bearing=90,own_speed=0,target_speed=0,distance=2000,shift=4,
         turn=0,heading=0,ammo=0,lead=True,shared_motion=False,
         step_history=None,flight_shifts=None):
    u=game.machine();theta=math.radians(bearing)
    relative=(-distance*4*math.sin(theta),-distance*4*math.cos(theta))
    own_v=(0,-own_speed*4)
    target_v=own_v if shared_motion else (-target_speed*4*math.cos(theta),target_speed*4*math.sin(theta))
    w16(u,STATE+0x6e,shift);w16(u,STATE+0xa6,OWN);w16(u,STATE+0xbe,3)
    w16(u,glob(0x1d0d4),1);w16(u,glob(0x1d0d6),TARGET)
    w16(u,UNITS+OWN+8,TARGET)
    sounds=[]
    u.hook_add(UC_HOOK_CODE,lambda uc,a,s,d:sounds.append(uc.reg_read(UC_M68K_REG_D1)&65535),
               begin=old(0x5e2c),end=old(0x5e2c))
    history=[]
    frame_shifts=list(step_history or [shift]*3)
    assert len(frame_shifts)==3 and frame_shifts[-1]==shift
    frame_times=[-1/(1<<frame_shifts[1])-1/(1<<frame_shifts[2]),-1/(1<<frame_shifts[2]),0]
    for t,frame_shift in zip(frame_times,frame_shifts):
        w16(u,STATE+0x6e,frame_shift)
        yaw=round((heading+turn*t)*65536/360)&65535
        w16(u,UNITS+OWN+0x28,yaw);w16(u,UNIT+0x10,yaw)
        for record,delta,velocity in ((OWN,(0,0),own_v),(TARGET,relative,target_v)):
            for axis,offset in enumerate((0x18,0x20)):
                w32(u,UNITS+record+offset,round((16000+delta[axis]+velocity[axis]*t)*65536))
            w32(u,UNITS+record+0x1c,100*65536)
            for axis,offset in enumerate((0x46,0x4e)):
                w32(u,UNITS+record+offset,round(velocity[axis]*65536))
        call(u,0x361e,regs={UC_M68K_REG_D4:OWN,UC_M68K_REG_A5:UNIT})
        history.append([r16(u,UNIT+0xe),r16(u,UNIT+0x64),word(r16(u,UNIT+0x66))])
    call(u,0x5730,stop=old(0x584c),regs={
        UC_M68K_REG_D0:r16(u,UNIT+0x2e),UC_M68K_REG_D1:r16(u,UNIT+0xe),
        UC_M68K_REG_D2:distance*4,UC_M68K_REG_D3:ammo,UC_M68K_REG_D4:OWN,
        UC_M68K_REG_D6:r16(u,UNIT+0x66) if lead else 0,UC_M68K_REG_A5:UNIT})
    velocity=list(struct.unpack('>3h',u.mem_read(u.reg_read(UC_M68K_REG_A1),6)))
    u.emu_start(old(0x584c),old(0x5838),count=1000000)
    assert u.reg_read(UC_M68K_REG_PC)==old(0x5838)
    assert not u.reg_read(UC_M68K_REG_SR)&1
    projectile=u.reg_read(UC_M68K_REG_D5)&65535
    stored=[r32(u,UNITS+projectile+o)/65536 for o in (0x46,0x4a,0x4e)]
    assert stored==velocity, (stored,velocity)
    pos=[r32(u,UNITS+projectile+o)/65536 for o in (0x18,0x1c,0x20)]
    call(u,0x623c,regs={UC_M68K_REG_D4:projectile})
    after=[r32(u,UNITS+projectile+o)/65536 for o in (0x18,0x1c,0x20)]
    assert [after[i]-pos[i] for i in range(3)]==[v/(1<<shift) for v in velocity]
    # Exercise the actual integrator across variable frame durations. Gravity
    # and collisions are outside this horizontal kinematic invariant.
    elapsed=1/(1<<shift)
    for flight_shift in flight_shifts or []:
        w16(u,STATE+0x6e,flight_shift)
        call(u,0x623c,regs={UC_M68K_REG_D4:projectile})
        elapsed+=1/(1<<flight_shift)
        actual=[r32(u,UNITS+projectile+o)/65536 for o in (0x18,0x1c,0x20)]
        expected=[((round((pos[i]+velocity[i]*elapsed)*65536)+0x80000000)%0x100000000-0x80000000)/65536
                  for i in range(3)]
        assert actual==expected,(actual,expected)
    muzzle=(pos[0]-16000,pos[2]-16000)
    displacement=[relative[i]-muzzle[i] for i in range(2)]
    rel_velocity=[velocity[(0,2)[i]]-target_v[i] for i in range(2)]
    time=sum(a*b for a,b in zip(displacement,rel_velocity))/sum(v*v for v in rel_velocity)
    miss=math.hypot(*(rel_velocity[i]*time-displacement[i] for i in range(2)))/4
    return dict(bearing=bearing,own_speed_mps=own_speed,target_speed_mps=target_speed,
                distance_m=distance,time_shift=shift,turn_dps=turn,heading=heading,ammo=ammo,
                shared_motion=shared_motion,lead=lead,tracking=history[-1],velocity=velocity,
                horizontal_miss_m=round(miss,4),sounds=sounds,projectile_integrator_verified=True)


def manual_checks(original,patched):
    checks=0
    # Explicit world-angle sequences include wrapping through 0/65535.
    for locked in (0,1):
        for angles,hulls in (([65520,65528,0,8],[0,0,0,0]),
                             ([1000]*4,[0,1000,2000,3000]),
                             ([1000,1010,1020,1030],[0,1000,2000,3000])):
            outcomes=[]
            for game in (original,patched):
                u=game.machine();w16(u,glob(0x1d0d4),locked)
                w16(u,STATE+0x6e,4);w16(u,STATE+0xa6,OWN)
                w16(u,UNIT+0xe,angles[0]);w16(u,UNITS+OWN+0x38,angles[0])
                w16(u,UNIT+0x64,angles[0]-hulls[0])
                rows=[];sounds=[]
                u.hook_add(UC_HOOK_CODE,lambda uc,a,s,d:sounds.append(uc.reg_read(UC_M68K_REG_D1)&65535),
                           begin=old(0x5e2c),end=old(0x5e2c))
                for yaw,hull in zip(angles,hulls):
                    previous=r16(u,UNIT+0xe)
                    w16(u,UNIT+0x10,hull);w16(u,UNITS+OWN+0x28,hull)
                    call(u,0x36c2,regs={UC_M68K_REG_D0:0,UC_M68K_REG_D1:yaw,
                                       UC_M68K_REG_D4:OWN,UC_M68K_REG_A5:UNIT})
                    actual=r16(u,UNIT+0xe)
                    if game is patched:
                        assert word(r16(u,UNIT+0x66))==word(actual-previous)
                    rows.append((actual,r16(u,UNIT+0x64),r16(u,UNIT+0x2e)))
                outcomes.append((rows,sounds,u.reg_read(UC_M68K_REG_A7)))
            assert outcomes[0]==outcomes[1],outcomes
            assert outcomes[1][-1]==STACK+4
            checks+=1
    return checks


def verify(original_blob,patched_blob):
    original,patched=Game(original_blob),Game(patched_blob)
    manual=manual_checks(original,patched)
    stationary=[];shared=[];turns=[];sweeps=[]
    # Preserve the exact original shot vector against moving targets at rest,
    # with multiple bearings, hull headings, time steps, ranges and ammo types.
    for shift in range(5):
        for ammo in (0,3):
            for bearing in (-179,-90,-45,0,45,90,179):
                for speed in (-10,0,10):
                    args=dict(bearing=bearing,target_speed=speed,shift=shift,ammo=ammo,
                              heading=73,distance=1000 if ammo==3 else 2000)
                    a,b=shot(original,**args),shot(patched,**args)
                    assert a['velocity']==b['velocity'] and a['tracking']==b['tracking'],(a,b)
                    assert a['sounds']==b['sounds']
                    stationary.append(b)
            for speed in (-15,15):
                for bearing in (-90,90):
                    args=dict(bearing=bearing,own_speed=speed,shared_motion=True,shift=shift,ammo=ammo)
                    a,b=shot(original,**args),shot(patched,**args)
                    assert b['horizontal_miss_m']==0,(a,b)
                    shared.append(dict(before=a,after=b))
            for bearing in (-90,0,45,90):
                for own,target in ((0,0),(0,10),(15,0),(15,10)):
                    args=dict(bearing=bearing,own_speed=own,target_speed=target,shift=shift,ammo=ammo)
                    straight=shot(patched,**args)
                    for turn in (-5,-1,1,5):
                        turning=shot(patched,**args,turn=turn)
                        assert straight['velocity']==turning['velocity'],(straight,turning)
                        assert straight['tracking'][2]==turning['tracking'][2]
                        turns.append(turning)
    # A quantitative directional sweep also checks the lead remains effective.
    for bearing in range(-180,180,5):
        a=shot(patched,bearing=bearing,target_speed=10)
        b=shot(patched,bearing=bearing,target_speed=10,lead=False)
        c=shot(original,bearing=bearing,own_speed=15)
        d=shot(patched,bearing=bearing,own_speed=15)
        sweeps.append(dict(stationary_with_lead=a,stationary_without_lead=b,moving_before=c,moving_after=d))
    means={key:round(statistics.mean(r[key]['horizontal_miss_m'] for r in sweeps),4) for key in sweeps[0]}
    assert means['stationary_with_lead']<means['stationary_without_lead']*0.5,means
    assert means['moving_after']<means['moving_before']*0.5,means
    return dict(all_passed=True,manual_and_wrap_cases=manual,stationary_regression_cases=len(stationary),
                shared_translation_cases=len(shared),turn_invariance_cases=len(turns),
                directional_sweep_cases=len(sweeps),mean_horizontal_miss_m=means,
                shared_translation=shared,scope='68000 tracking/launch/allocation/integration, no terrain collisions or random spread')


def game_from_adf(adf):
    from src.build_dark_green import open_adf, FSString
    dev,volume=open_adf(adf)
    game=bytes(volume.read_file(FSString('game')))
    volume.close();dev.close()
    return game


def verify_adf(adf):
    return verify(game_from_adf(SOURCE.read_bytes()),game_from_adf(adf))


if __name__=='__main__':
    path=Path(sys.argv[1]) if len(sys.argv)>1 else WORK/'ZoomF3_test.adf'
    report=verify_adf(path.read_bytes())
    write_json(WORK/'lead_standalone_tests.json',report)
    print({k:v for k,v in report.items() if k!='shared_translation'})
