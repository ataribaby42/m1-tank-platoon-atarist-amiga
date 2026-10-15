"""Deeper real-instruction regression tests for the restored Mi-24 call-in.

The deterministic flat battlefield is test data, not a replacement simulation.
Movement, navigation, collision registration, acquisition, firing, destruction,
cooldown and allocation execute the game binaries' own 68000 instructions.
For the original Mi-24 control only, call-in enters AFTER its broken guard.
This makes the original, otherwise unreachable flight code a useful oracle.
"""
from pathlib import Path
import hashlib
import struct
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.test_mi24 import (Runtime,formation_rows,ST_CODE,ST_DATA,amiga,st,
                          w16,w32,r16,r32,word,UNITS,RETURN,ROOT,SOURCE,WORK,STDisk)
from src.test_lead import STACK
from src.build_common import write_json
from unicorn import UC_HOOK_CODE
from unicorn.m68k_const import *

ST_CODE.update({0x4196:0x375e,0x5c3a:0x5208,0x2acc:0x2058,
                0x46e6:0x3cb0,0x512c:0x46f6,0x527c:0x4848,0x5630:0x4bfc})
ST_DATA.update({0x1f9ba:0x1123e,0x1f9fe:0x11282})
SHARED=0x6000000


def flat_world(rt,u):
    """One BSP leaf and one zero-height navigation landmark; no mock routines."""
    world=SHARED+0x90c
    tree,links,objects,terrain=[SHARED+p for p in (0x1000,0x2000,0x3000,0x4000)]
    for offset,pointer in ((0,tree),(4,links),(8,objects),(14,terrain)):
        w32(u,world+offset,pointer)
    w16(u,world+12,0);w16(u,world+18,1)
    w16(u,tree,16384);u.mem_write(links,b'\x80\x80'+b'\xff'*254)
    u.mem_write(terrain,struct.pack('>8H',0,32767,16000,0,32767,16000,0,0))
    for address in (0x1f9ba,0x1f9fe):u.mem_write(rt.data(address),b'\xff'*68)
    for slot in range(0,0x1800,128):w16(u,UNITS+slot+6,65535)


def construct(rt,u,type_id,x=-1000,z=-1000):
    rt.call(u,0x6c76,{UC_M68K_REG_D0:x&65535,UC_M68K_REG_D2:z&65535,
        UC_M68K_REG_D1:r16(u,rt.state+0x294),UC_M68K_REG_D3:type_id,UC_M68K_REG_D6:0})
    assert not u.reg_read(UC_M68K_REG_SR)&1,'Unit constructor exhausted'
    return u.reg_read(UC_M68K_REG_D5)&65535


def setup(rt,type_id=31,shift=0,row=0,cpu=UC_CPU_M68K_M68000):
    u,army=rt.machine([formation_rows(rt.platform)[row]] if type_id==31 else [],shift,cpu)
    flat_world(rt,u)
    slot=rt.records(u)[31][0] if type_id==31 else construct(rt,u,type_id)
    w16(u,rt.state+0x20,(239,0,42,1000,32767,65535,1337,4096)[row])
    return u,slot


def dispatch(rt,u,slot):
    """Use the same relocated class table as the full game's unit dispatcher."""
    cls=word(r16(u,UNITS+slot+4))
    if cls<0:return
    assert cls%2==0 and cls<=34,cls
    table=amiga.old(0x231c) if rt.platform=='amiga' else st.BASE+0x1898
    pc=r32(u,table+cls*2)
    u.reg_write(UC_M68K_REG_D4,slot);u.reg_write(UC_M68K_REG_A5,r32(u,UNITS+slot))
    u.reg_write(UC_M68K_REG_A7,STACK);w32(u,STACK,RETURN)
    u.emu_start(pc,RETURN,count=1000000)
    assert u.reg_read(UC_M68K_REG_PC)==RETURN,hex(u.reg_read(UC_M68K_REG_PC))


def call_in(rt,u,slot,type_id,original=False):
    w16(u,UNITS+slot+0x62,command_for(type_id))
    if original and type_id==31:
        # Deliberately bypass ONLY the old, proven-broken call guard.
        rt.call(u,0x4196,{UC_M68K_REG_D4:slot,UC_M68K_REG_A5:r32(u,UNITS+slot)})
        # A normal tick also rotates the rotor and publishes the old state.
        w16(u,UNITS+slot+0x38,r16(u,UNITS+slot+0x38)+0x36be)
        w16(u,r32(u,UNITS+slot)+0x1a,0)
    else:dispatch(rt,u,slot)
    assert r16(u,UNITS+slot+0x40)==1


def command_for(type_id):
    return 0x6a6a if type_id in (8,30) else 0x6f6f if type_id==10 else 0x6161


def fingerprint(rt,u,slot):
    # Absolute pointers in records and aux data are stable within each platform.
    return (bytes(u.mem_read(UNITS,0x1800)),bytes(u.mem_read(r32(u,UNITS+slot),0x40)),
            r16(u,rt.state+0x20),bytes(u.mem_read(SHARED+0x1000,0x3100)),
            bytes(u.mem_read(rt.data(0x1f9ba),136)))


def cycles(original,patched,type_id,shift,row=0,cpu=UC_CPU_M68K_M68000):
    pair=[setup(rt,type_id,shift,row,cpu) for rt in (original,patched)]
    result=[]
    for cycle in range(2):
        for rt,(u,slot) in zip((original,patched),pair):call_in(rt,u,slot,type_id,rt is original)
        phases=[1];moved=False;first=None
        for tick in range(1600*(1<<shift)):
            for rt,(u,slot) in zip((original,patched),pair):
                if tick%17==0:w16(u,UNITS+slot+0x62,command_for(type_id))
                dispatch(rt,u,slot)
            assert fingerprint(original,*pair[0])==fingerprint(patched,*pair[1]),(type_id,shift,row,cycle,tick)
            u,slot=pair[1];state=r16(u,UNITS+slot+0x40)
            if state!=phases[-1]:phases.append(state)
            if state==2:
                pos=tuple(word(r16(u,UNITS+slot+p)) for p in (0x18,0x20))
                if first is None:first=pos
                moved|=pos!=first
                assert r16(u,UNITS+slot+4)==(24 if type_id in (8,30) else 14)
            if state==0:break
        else:raise AssertionError(('Lifecycle timeout',type_id,shift,row,phases))
        assert phases==[1,2,3,4,0] and moved,phases
        assert r16(u,UNITS+slot+6)==65535,'Off-map helicopter leaked a spatial slot'
        for rt,(u,slot) in zip((original,patched),pair):
            for _ in range(20):
                dispatch(rt,u,slot);assert r16(u,UNITS+slot+0x40)==0
        result.append(dict(ticks=tick+1,states=phases,moved=True))
    return dict(type=type_id,time_shift=shift,formation=row,cpu=cpu,cycles=result,
                every_tick_matches_original=True,spatial_slots_released=True)


def combat(rt,shift,cpu,original=False):
    u,slot=setup(rt,shift=shift,cpu=cpu)
    target=construct(rt,u,0,15500,16000)
    w16(u,rt.state+0xa6,target)
    rt.call(u,0x5c3a,{UC_M68K_REG_D4:target})
    call_in(rt,u,slot,31,original)
    fired=[];acquired=False;projectile_moved=False;hits=0
    trajectory=hashlib.sha256()
    u.hook_add(UC_HOOK_CODE,lambda uc,a,s,d:fired.append(r16(uc,UNITS+slot+8)),
               begin=rt.code(0x512c),end=rt.code(0x512c))
    for tick in range(400*(1<<shift)):
        rt.tick(u,slot)
        acquired|=r16(u,UNITS+slot+8)==target
        for p in range(0,0x1800,128):
            if r16(u,UNITS+p+4) in (4,6,8,10,12,16,18,20):
                before=bytes(u.mem_read(UNITS+p+0x18,12));dispatch(rt,u,p)
                projectile_moved|=before!=bytes(u.mem_read(UNITS+p+0x18,12))
        if r16(u,UNITS+target+0xe)!=65535:
            hits+=1
            rt.call(u,0x2acc,{UC_M68K_REG_D4:target,UC_M68K_REG_A5:r32(u,UNITS+target)})
        trajectory.update(bytes(u.mem_read(UNITS,0x1800)))
        trajectory.update(bytes(u.mem_read(r32(u,UNITS+slot),0x40)))
        if fired and projectile_moved and hits:break
    assert acquired and fired and projectile_moved,(shift,acquired,len(fired),projectile_moved)
    assert set(fired)=={target},fired
    return dict(time_shift=shift,cpu=cpu,acquired_friendly_tank=True,
                attack_calls=len(fired),projectile_movement=True,registered_hits=hits,ticks=tick+1,
                trajectory_sha256=trajectory.hexdigest())


def all_commands(original,patched):
    """Every command byte and state, with unrelated registers preserved."""
    machines=[rt.game.machine(supervisor=False) for rt in (original,patched)]
    regs=[UC_M68K_REG_D0,UC_M68K_REG_D1,UC_M68K_REG_D2,UC_M68K_REG_D3,
          UC_M68K_REG_D4,UC_M68K_REG_D5,UC_M68K_REG_D6,UC_M68K_REG_D7,
          UC_M68K_REG_A0,UC_M68K_REG_A1,UC_M68K_REG_A4,UC_M68K_REG_A5,UC_M68K_REG_A6]
    slot=0x580;checks=0
    for ident in list(range(32))+[0x112,0xff12,65535]:
        for command in list(range(256))+[0x6161,0xff61,0x6f6f,0xff6f,0x6a6a,0xff00]:
            for state in range(6):
                snapshots=[]
                for rt,u in zip((original,patched),machines):
                    u.mem_write(UNITS+slot,b'\x5a'*128)
                    w16(u,UNITS+slot+0x6a,ident);w16(u,UNITS+slot+0x62,command)
                    w32(u,rt.data(0x3675a),0x12345678)
                    values={r:0x100+i for i,r in enumerate(regs)}
                    values.update({UC_M68K_REG_D0:state,UC_M68K_REG_D2:0,UC_M68K_REG_D4:slot})
                    rt.call(u,0x4110,values)
                    snapshots.append((bytes(u.mem_read(UNITS+slot,128)),r32(u,rt.data(0x3675a)),
                                      tuple(u.reg_read(r) for r in regs),u.reg_read(UC_M68K_REG_A7)))
                if ident==18 and command&255==0x61:
                    record=bytearray(snapshots[0][0]);struct.pack_into('>H',record,0x62,command)
                    expected=list(snapshots[0][2]);expected[2]=command
                    assert snapshots[1]==(bytes(record),0x12345678,tuple(expected),snapshots[0][3])
                else:assert snapshots[0]==snapshots[1],(ident,command,state)
                checks+=1
    return checks


def destruction(rt,shift,cpu):
    u,slot=setup(rt,shift=shift,cpu=cpu);call_in(rt,u,slot,31)
    while r16(u,UNITS+slot+0x40)!=2:rt.tick(u,slot)
    for _ in range(8*(1<<shift)):rt.tick(u,slot)
    # Apply the terminal damage state that the original damage routine produces.
    w16(u,r32(u,UNITS+slot)+4,3)
    for ticks in range(100*(1<<shift)):
        rt.tick(u,slot)
        if r16(u,UNITS+slot+4)==22:break
    else:raise AssertionError('Damaged Mi-24 never became a wreck')
    for _ in range(200*(1<<shift)):
        w16(u,UNITS+slot+0x62,0x6161);dispatch(rt,u,slot)
        assert r16(u,UNITS+slot+4)==22
        assert r16(u,UNITS+slot+0x40)==5
    return dict(time_shift=shift,cpu=cpu,crash_ticks=ticks+1,wreck_cannot_respawn=True)


def verify(original_blob,patched_blob,platform):
    original,patched=[Runtime(b,platform) for b in (original_blob,patched_blob)]
    lifecycle=[]
    guards=all_commands(original,patched)
    for type_id in (31,9,10):
        for shift in range(5):lifecycle.append(cycles(original,patched,type_id,shift))
    for row in range(1,8):lifecycle.append(cycles(original,patched,31,0,row))
    lifecycle.append(cycles(original,patched,31,4,cpu=UC_CPU_M68K_M68020))
    for type_id in (8,30):
        for shift in (0,4):lifecycle.append(cycles(original,patched,type_id,shift))
    fighting=[];crashes=[]
    for shift in range(5):
        result=combat(patched,shift,UC_CPU_M68K_M68000)
        assert result==combat(original,shift,UC_CPU_M68K_M68000,original=True)
        fighting.append(dict(**result,identical_to_original=True))
        crashes.append(destruction(patched,shift,UC_CPU_M68K_M68000))
    result=combat(patched,4,UC_CPU_M68K_M68020)
    assert result==combat(original,4,UC_CPU_M68K_M68020,original=True)
    fighting.append(dict(**result,identical_to_original=True))
    crashes.append(destruction(patched,4,UC_CPU_M68K_M68020))
    return dict(all_passed=True,platform=platform,exhaustive_guard_cases=guards,lifecycles=lifecycle,combat=fighting,
                destruction=crashes,sha256=hashlib.sha256(patched_blob).hexdigest(),
                scope='Real 68000 instructions on a deterministic flat battlefield. Original Mi-24 '
                      'control bypasses its broken call guard only; no movement/combat routines mocked. '
                      'Not a full visual mission or a hardware performance benchmark.')


if __name__=='__main__':
    for platform in sys.argv[1:] or ('amiga','st'):
        if platform=='amiga':
            before=amiga.game_from_adf(SOURCE.read_bytes())
            after=amiga.game_from_adf((ROOT/'output/M1TankPlatoon_modded.adf').read_bytes())
        else:
            before=STDisk((ROOT/'assets/M1 Tank Platoon.st').read_bytes()).read('GAME.PRG')
            after=STDisk((ROOT/'output/M1TankPlatoon_modded.st').read_bytes()).read('GAME.PRG')
        result=verify(before,after,platform)
        write_json(WORK/('mi24_lifecycle_tests.json' if platform=='amiga' else 'st/mi24_lifecycle_tests.json'),result)
        print(platform,'extended Mi-24 regression tests passed.',flush=True)
