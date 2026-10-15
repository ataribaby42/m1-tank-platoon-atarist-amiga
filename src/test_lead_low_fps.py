"""Low-FPS and changing-timestep regression checks for the shipped ADFs."""
from pathlib import Path
from hashlib import sha256
import statistics
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.build_common import ROOT,WORK,write_json
from src.test_lead import Game,game_from_adf,shot,call,w16,r16,STATE


def verify(path):
    blob=path.read_bytes();game=Game(game_from_adf(blob))
    calibration=[]
    u=game.machine()
    # Execute the game's actual initial timing calibration (timer ticks).
    for ticks in (1,2,3,4,7,8,15,16,30,31,60):
        for off,value in ((0x5a,4),(0x64,0),(0xc4,0xffff),(0x56,100+ticks),(0x58,100),(0xbe,3)):
            w16(u,STATE+off,value)
        call(u,0x227c)
        calibration.append(dict(frame_timer_ticks=ticks,shift=r16(u,STATE+0x6e)))
    assert [r['shift'] for r in calibration]==[4,4,4,3,3,2,2,1,1,0,0]
    fixed=[];transition_count=0
    for shift in range(5):
        rows=[]
        for ammo in (0,3):
            for bearing in range(-180,180,15):
                for own,target in ((0,10),(15,0),(15,10),(-15,10)):
                    straight=shot(game,bearing=bearing,own_speed=own,target_speed=target,shift=shift,ammo=ammo)
                    turning=shot(game,bearing=bearing,own_speed=own,target_speed=target,shift=shift,ammo=ammo,turn=5)
                    assert straight['velocity']==turning['velocity']
                    rows.append(straight)
            for previous in range(5):
                for own,target in ((0,10),(15,0),(15,10)):
                    for bearing in (-90,0,75,90):
                        args=dict(bearing=bearing,own_speed=own,target_speed=target,shift=shift,ammo=ammo,turn=-5)
                        steady=shot(game,**args)
                        changed=shot(game,**args,step_history=[previous,previous,shift],
                                     flight_shifts=[4,0,3,1,2,4,0,4])
                        assert changed['velocity']==steady['velocity'],(changed,steady)
                        assert changed['tracking']==steady['tracking']
                        transition_count+=1
        fixed.append(dict(shift=shift,step_base_time=1/(1<<shift),cases=len(rows),
                          mean_horizontal_miss_m=round(statistics.mean(r['horizontal_miss_m'] for r in rows),4),
                          max_horizontal_miss_m=max(r['horizontal_miss_m'] for r in rows)))
    assert sha256(path.read_bytes()).digest()==sha256(blob).digest()
    return dict(adf=str(path.relative_to(ROOT)),sha256=sha256(blob).hexdigest(),all_passed=True,
                calibration=calibration,fixed_steps=fixed,transition_cases=transition_count,
                flight_steps_per_transition=9,
                scope='Real 68000 tracking, launch and position integrator. Controlled planar motion, no random spread or terrain collisions. Frame steps are simulation time, not measured host FPS.')


if __name__=='__main__':
    reports=[verify(p) for p in sorted((ROOT/'output').glob('*.adf'))]
    write_json(WORK/'lead_low_fps_tests.json',dict(all_passed=True,adfs=reports))
    for report in reports:print(report)
