"""Run real 68000 support forwarding, helicopter guards, timers and arrivals."""
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import test_lead as amiga
from src import test_st as st
from src.test_lead import w16,w32,r16,r32,word,UNITS,UNIT,RETURN
from src.build_common import ROOT,SOURCE,WORK,write_json
from src.st_disk import STDisk
from src.st_executable import TOSExecutable
from src.build_dark_green import open_adf,FSString
from unicorn.m68k_const import *

ST_CODE={0x4110:0x36d8,0x3fce:0x3596,0xba2a:0xb0e0,0x6c76:0x6252,
         0x50fe:0x46c8,0x9836:0x8ebe}
ST_DATA={0x3a094:0x2b93e,0x3a716:0x2bfc0,0x3675a:0x27f8e}


class Runtime:
    def __init__(self,blob,platform):
        self.platform=platform
        self.game=(amiga.Game if platform=='amiga' else st.Game)(blob)
        self.state=amiga.STATE if platform=='amiga' else st.STATE
        self.data=amiga.glob if platform=='amiga' else lambda a:st.BASE+ST_DATA[a]
        self.code=amiga.old if platform=='amiga' else lambda a:st.BASE+ST_CODE[a]

    def call(self,u,a,regs=None):
        if self.platform=='amiga':amiga.call(u,a,regs=regs)
        else:st.call(u,ST_CODE[a],regs=regs)

    def machine(self,rows=(),shift=4,cpu=UC_CPU_M68K_M68000):
        u=self.game.machine(cpu_model=cpu,supervisor=False)
        shared=0x6000000
        u.mem_map(shared,0x10000)
        w32(u,r32(u,self.code(0xba2a)+2),shared)
        u.mem_write(shared+0x3b0,b''.join(rows))
        for addr,n in ((0x3a094,0x110),(0x3a716,0x40)):
            u.mem_write(self.data(addr),b'\xff'*n)
        for off in range(0,0x1800,0x80):w16(u,UNITS+off+4,0xffff)
        w16(u,self.state+0x26c,2)
        w16(u,self.state+0x6e,shift)
        self.call(u,0xba2a)
        army=r16(u,self.data(0x3a094)+r16(u,self.state+0x294))
        w16(u,self.state+0x4c,army)
        return u,army

    def records(self,u):
        result={}
        for off in range(0,0x1800,0x80):
            if r16(u,UNITS+off+4)!=0xffff:
                result.setdefault(r16(u,r32(u,UNITS+off)),[]).append(off)
        return result

    def tick(self,u,slot):
        self.call(u,0x3fce,{UC_M68K_REG_D4:slot,UC_M68K_REG_A5:r32(u,UNITS+slot)})

    def forward(self,u,army,ground):
        # The spotted target is a fixture. Support command, organization,
        # propagation and the helicopter itself come from the real loader.
        target=0x1700
        w16(u,UNITS+target+0x18,16000)
        w16(u,UNITS+target+0x20,16000)
        w16(u,UNITS+ground+8,target)
        self.call(u,0x50fe,{UC_M68K_REG_D4:ground,UC_M68K_REG_A5:r32(u,UNITS+ground)})
        assert r16(u,UNITS+army+0x62)==0x6161
        self.call(u,0x9836,{UC_M68K_REG_D4:army})


def formation_rows(platform):
    if platform=='amiga':
        dev,vol=open_adf(SOURCE.read_bytes())
        try:blob=bytes(vol.read_file(FSString('tankst')))
        finally:vol.close();dev.close()
        base=0x20286
    else:
        blob=TOSExecutable(STDisk((ROOT/'assets/M1 Tank Platoon.st').read_bytes()).read('TANKST.PRG')).image
        base=0x18f8a
    return [bytes(blob[base+i*98:base+(i+1)*98]) for i in (57,58,59,60,69,70,71,72)]


def guard_checks(original,patched):
    pair=[r.game.machine(supervisor=False) for r in (original,patched)]
    slot=0x580
    checks=0
    for identifier in range(32):
        for command in (0,0x61,0x6161,0x6f,0x6f6f,0x6a6a,0xffff):
            for state in range(6):
                records=[]
                for runtime,u in zip((original,patched),pair):
                    u.mem_write(UNITS+slot,bytes(128))
                    w16(u,UNITS+slot+0x6a,identifier)
                    w16(u,UNITS+slot+0x62,command)
                    w32(u,runtime.data(0x3675a),0x12345678)
                    runtime.call(u,0x4110,{UC_M68K_REG_D0:state,UC_M68K_REG_D1:1234,
                                         UC_M68K_REG_D2:0,UC_M68K_REG_D3:5678,UC_M68K_REG_D4:slot})
                    records.append((bytes(u.mem_read(UNITS+slot,128)),r32(u,runtime.data(0x3675a)),
                                    [u.reg_read(r) for r in (UC_M68K_REG_D0,UC_M68K_REG_D1,UC_M68K_REG_D2,UC_M68K_REG_D3)]))
                if identifier==18 and command&255==0x61:
                    assert r16(pair[0],UNITS+slot+0x62)==0
                    assert r16(pair[1],UNITS+slot+0x62)==command
                    assert records[1][1]==0x12345678
                    assert records[1][2]==[state,1234,command,5678]
                else:assert records[0]==records[1],(identifier,command,state)
                checks+=1
    return checks


def arrive(runtime,u,slot,shift,repeat_command=0):
    assert r16(u,UNITS+slot+0x40)==1
    delay=r16(u,UNITS+slot+0x2c)
    assert 30*(1<<shift)<=delay<=61*(1<<shift)
    for _ in range(delay):
        if repeat_command:w16(u,UNITS+slot+0x62,repeat_command)
        runtime.tick(u,slot)
        assert r16(u,UNITS+slot+0x40)==1
        assert word(r16(u,UNITS+slot+0x18))==-1000
    runtime.tick(u,slot)
    assert r16(u,UNITS+slot+0x40)==2
    x,y,z=[word(r16(u,UNITS+slot+p)) for p in (0x18,0x1c,0x20)]
    assert x in (16,32751) and y==120 and 8192<=z<=24575,(x,y,z)
    assert r16(u,UNITS+slot+4)==14 and r16(u,UNITS+slot+0x36)==3
    return dict(delay_ticks=delay,delay_seconds=delay/(1<<shift),arrival_xyz=[x,y,z],
                model=r16(u,UNITS+slot+0x24))


def verify(original_blob,patched_blob,platform):
    original,patched=[Runtime(b,platform) for b in (original_blob,patched_blob)]
    guards=guard_checks(original,patched)
    cases=[]
    for index,row in enumerate(formation_rows(platform)):
        assert struct.unpack_from('>H',row,20)[0]==31
        for shift in range(5):
            for runtime in (original,patched):
                u,army=runtime.machine([row],shift)
                w16(u,runtime.state+0x20,(239,0,42,1000,32767,65535,1337,4096)[index])
                units=runtime.records(u)
                slot=units[31][0]
                ground=next(offsets[0] for t,offsets in units.items() if 11<=t<=28)
                assert r16(u,r32(u,UNITS+ground)+0x2a)==0x6161
                assert r16(u,UNITS+slot+0x6a)==18
                assert word(r16(u,UNITS+slot+0x18))==-1000
                for _ in range(3):runtime.tick(u,slot)
                assert r16(u,UNITS+slot+0x40)==0  # No automatic spawn without a call.
                runtime.forward(u,army,ground)
                assert r16(u,UNITS+slot+0x62)==0x6161
                w32(u,runtime.data(0x3675a),0x12345678)
                runtime.tick(u,slot)
                if runtime is original:
                    assert r16(u,UNITS+slot+0x40)==0
                    assert r16(u,UNITS+slot+0x62)==0
                    continue
                result=arrive(runtime,u,slot,shift,repeat_command=0x6161)
                assert result['arrival_xyz'][0]==32751 and result['model']==17
                assert r32(u,runtime.data(0x3675a))==0x12345678
                cases.append(dict(formation=index,time_shift=shift,**result))
    controls=[]
    for type_id,command in ((9,0x6161),(10,0x6f6f)):
        for shift in (0,4):
            states=[]
            for runtime in (original,patched):
                u,army=runtime.machine(shift=shift)
                runtime.call(u,0x6c76,{UC_M68K_REG_D0:64536,UC_M68K_REG_D2:64536,
                    UC_M68K_REG_D1:r16(u,runtime.state+0x294),UC_M68K_REG_D3:type_id,UC_M68K_REG_D6:0})
                assert not u.reg_read(UC_M68K_REG_SR)&1
                slot=u.reg_read(UC_M68K_REG_D5)&65535
                w16(u,UNITS+slot+0x62,command)
                runtime.tick(u,slot)
                states.append(arrive(runtime,u,slot,shift))
            assert states[0]==states[1]
            controls.append(dict(type=type_id,time_shift=shift,unchanged=True,**states[1]))
    unavailable=0
    for cpu in (UC_CPU_M68K_M68000,UC_CPU_M68K_M68020):
        for runtime in (original,patched):
            u,army=runtime.machine([formation_rows(platform)[0]],cpu=cpu)
            slot=runtime.records(u)[31][0]
            w16(u,UNITS+slot+0x36,0xffff)
            w16(u,UNITS+slot+0x62,0x6161)
            for _ in range(3):runtime.tick(u,slot)
            assert r16(u,UNITS+slot+0x40)==5
            assert word(r16(u,UNITS+slot+0x18))==-1000
            unavailable+=1
        u,army=patched.machine([formation_rows(platform)[0]],cpu=cpu)
        slot=patched.records(u)[31][0]
        w16(u,UNITS+slot+0x62,0x6161)
        patched.tick(u,slot)
        arrive(patched,u,slot,4)
    return dict(all_passed=True,platform=platform,guard_regression_cases=guards,
                mi24_arrival_cases=cases,friendly_arrival_controls=controls,
                real_ground_to_army_to_helicopter_command=True,
                all_five_time_steps=True,user_mode_68000_and_68020=True,
                unavailable_helicopter_checks=unavailable,
                no_call_no_spawn=True,no_false_friendly_radio=True,
                scope='Original 68000 loading, command routing, countdown and arrival; not a visual mission playthrough.')


if __name__=='__main__':
    for platform in ('amiga','st'):
        if platform=='amiga':
            before=amiga.game_from_adf(SOURCE.read_bytes())
            after=amiga.game_from_adf((ROOT/'output/M1TankPlatoon_modded.adf').read_bytes())
        else:
            before=STDisk((ROOT/'assets/M1 Tank Platoon.st').read_bytes()).read('GAME.PRG')
            after=STDisk((ROOT/'output/M1TankPlatoon_modded.st').read_bytes()).read('GAME.PRG')
        result=verify(before,after,platform)
        write_json(WORK/('mi24_tests.json' if platform=='amiga' else 'st/mi24_tests.json'),result)
        print(platform,'Mi-24 and friendly support checks passed.')
