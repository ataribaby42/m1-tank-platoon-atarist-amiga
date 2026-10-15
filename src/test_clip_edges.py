"""Run real 68000 clipping, edge accumulation and planar polygon filling."""
from pathlib import Path
from fractions import Fraction
import math
import random
import struct
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.test_lead import Game,game_from_adf,call,w16,w32,r16,STATE,old,glob,BASE,RETURN
from src.build_common import SOURCE,WORK,write_json
from unicorn import UC_HOOK_CODE
from unicorn.m68k_const import *
from PIL import Image,ImageDraw,ImageFilter,ImageChops

SCREEN=0x5000000
BITMAP=SCREEN+0x9000
EDGE=SCREEN+0xa000
VIEWPORTS=[(96,6,216,116),(64,10,257,187),(0,0,319,191)]


def setup(game,viewport,**machine_options):
    u=game.machine(**machine_options);u.mem_map(SCREEN,0x10000)
    u.mem_write(BITMAP,struct.pack('>HHBBH4I',40,200,0,4,0,*[SCREEN+8000*p for p in range(4)]))
    w32(u,glob(0x1cfc8),BITMAP)
    u.mem_write(BASE[15],bytes.fromhex('7fff8001')*200)
    w16(u,BASE[15]+0x462,199);w16(u,BASE[15]+0x466,0)
    for off,value in zip((0x1fc,0x204,0x200,0x208),viewport):w16(u,STATE+off,value)
    w16(u,STATE+0xc,2)
    call(u,0xb3d6)
    return u


def clip_edge(u,points,viewport):
    (x0,y0),(x1,y1)=points
    u.mem_write(EDGE,struct.pack('>8H',*[n&65535 for n in (0,x0,y0,y0,0,x1,y1,y1)]))
    call(u,0xcf04,regs={UC_M68K_REG_D2:x0&0xffffffff,UC_M68K_REG_D3:y0&0xffffffff,
                       UC_M68K_REG_D4:x1&0xffffffff,UC_M68K_REG_D5:y1&0xffffffff,
                       UC_M68K_REG_A0:viewport[0],UC_M68K_REG_A1:viewport[1],
                       UC_M68K_REG_A5:viewport[2],UC_M68K_REG_A6:viewport[3],UC_M68K_REG_A4:EDGE})
    return list(struct.unpack('>8h',u.mem_read(EDGE,16)))


def render_polygon(game,points,viewport=VIEWPORTS[1]):
    u=setup(game,viewport)
    records=[]
    for a,b in zip(points,points[1:]+points[:1]):
        records.append(clip_edge(u,[a,b],viewport))
        call(u,0xb250,regs={UC_M68K_REG_A4:EDGE})
    edges=[r16(u,STATE+o) for o in (0x110,0x112,0x114,0x116)]
    call(u,0xb3d6)
    plane=bytes(u.mem_read(SCREEN+8000,8000))
    im=Image.frombytes('1',(320,200),plane).convert('L')
    # All writes must be in the viewport; the adjacent cockpit/status stays intact.
    exterior=im.copy();ImageDraw.Draw(exterior).rectangle(viewport,fill=0)
    assert exterior.getbbox() is None,(points,viewport,'write outside viewport')
    return im,dict(records=records,boundary_extents=edges)


def reference_polygon(points,viewport):
    polygon=[tuple(Fraction(n) for n in p) for p in points]
    for axis,bound,lower in ((0,viewport[0],True),(0,viewport[2],False),
                              (1,viewport[1],True),(1,viewport[3],False)):
        result=[]
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            ia=a[axis]>=bound if lower else a[axis]<=bound
            ib=b[axis]>=bound if lower else b[axis]<=bound
            if ia:result.append(a)
            if ia!=ib:
                t=(bound-a[axis])/(b[axis]-a[axis])
                result.append(tuple(a[k]+t*(b[k]-a[k]) for k in (0,1)))
        polygon=result
        if not polygon:break
    im=Image.new('L',(320,200))
    if len(polygon)>=3:ImageDraw.Draw(im).polygon([(round(x),round(y)) for x,y in polygon],fill=255)
    return im


def verify_user_mode(original,patched):
    """Include the privilege rules Unicorn 2.1.4 does not enforce for MOVE SR."""
    checks=0
    for cpu in (UC_CPU_M68K_M68000,UC_CPU_M68K_M68020,UC_CPU_M68K_M68040):
        for viewport in VIEWPORTS:
            l,t,r,b=viewport
            machines=[setup(g,viewport,cpu_model=cpu,supervisor=False) for g in (original,patched)]
            if cpu!=UC_CPU_M68K_M68000:
                def forbid_move_from_sr(u,address,size,data):
                    opcode=r16(u,address)
                    assert opcode&0xffc0!=0x40c0, f'Privileged MOVE from SR at {address:x}'
                for u in machines:u.hook_add(UC_HOOK_CODE,forbid_move_from_sr)
            for points in ([(l-90,t+20),(l+26,b-20)],[(r+90,t+20),(r-26,b-20)],
                           [(l+10,t+20),(r-10,b-20)],[(l-90,t-20),(r+90,b+20)],
                           [(-120000,-120000),(120000,120000)],
                           [(l-100,t-100),(r+100,t-100)]):
                states=[]
                for u in machines:
                    edge=clip_edge(u,points,viewport)
                    registers=[u.reg_read(reg) for reg in
                        [UC_M68K_REG_D0+i for i in range(8)]+[UC_M68K_REG_A0+i for i in range(8)]]
                    probe=RETURN+0x100
                    # MOVE CCR is legal on 68010+, MOVE SR is legal on 68000.
                    opcode=b'\x40\xf9' if cpu==UC_CPU_M68K_M68000 else b'\x42\xf9'
                    u.mem_write(probe,opcode+struct.pack('>I',EDGE+32)+b'\x4e\x71')
                    u.emu_start(probe,probe+8,count=10)
                    states.append(([edge[i] for i in (0,1,3,5,7)],registers,r16(u,EDGE+32)&31))
                assert states[0]==states[1],(cpu,points,states)
                checks+=1
    return dict(cpus=['68000','68020','68040'],user_mode_line_cases=checks,
                privileged_sr_reads_rejected=True,condition_codes_preserved=True)


def verify(original_blob,patched_blob):
    original,patched=Game(original_blob),Game(patched_blob)
    user_mode=verify_user_mode(original,patched)
    # Exact reproduction of the reported vertical tails on either border.
    cases=[('left',[(-30,30),(90,115),(-30,115)],64,96),
           ('right',[(340,30),(225,115),(340,115)],257,91)]
    for name,points,x,first in cases:
        before,_=render_polygon(original,points)
        after,_=render_polygon(patched,points)
        assert [y for y in range(200) if before.getpixel((x,y))]==list(range(30,116))
        assert [y for y in range(200) if after.getpixel((x,y))]==list(range(first,116))
        before.save(WORK/f'edge_{name}_before.png');after.save(WORK/f'edge_{name}_after.png')
    rng=random.Random(68000)
    inside=outside=covered=shape_count=line_count=horizon_count=0
    for viewport in VIEWPORTS:
        l,t,r,b=viewport
        u0,u1=setup(original,viewport),setup(patched,viewport)
        for n in range(220):
            scale=120000 if n>=200 else 900
            pts=[(rng.randrange(-scale,scale),rng.randrange(-scale,scale)) for _ in range(2)]
            a=clip_edge(u0,pts,viewport);c=clip_edge(u1,pts,viewport)
            assert [a[i] for i in (0,1,3,5,7)]==[c[i] for i in (0,1,3,5,7)],(pts,a,c)
            for reg in [UC_M68K_REG_D0+i for i in range(8)]+[UC_M68K_REG_A0+i for i in range(8)]:
                assert u0.reg_read(reg)==u1.reg_read(reg),(pts,reg)
            # Materialize Unicorn's lazy condition flags with MOVE SR; its
            # direct reg_read(SR) may otherwise report stale condition bits.
            for u in (u0,u1):
                probe=RETURN+0x100
                u.mem_write(probe,b'\x40\xf9'+struct.pack('>I',EDGE+32)+b'\x4e\x71')
                u.emu_start(probe,probe+8,count=10)
            assert r16(u0,EDGE+32)==r16(u1,EDGE+32),(pts,'condition flags')
            line_count+=1
        for i in range(8):
            pts=[(l+10+i,t+10),(r-10,t+20+i),(l+30,b-10)]
            a,_=render_polygon(original,pts,viewport);c,_=render_polygon(patched,pts,viewport)
            assert a.tobytes()==c.tobytes()
            inside+=1
        for pts in ([(-900,-900),(900,-900),(900,t-10),(-900,t-10)],
                    [(-900,b+10),(900,b+10),(900,900),(-900,900)],
                    [(-900,-900),(l-10,-900),(l-10,900),(-900,900)],
                    [(r+10,-900),(900,-900),(900,900),(r+10,900)]):
            im,_=render_polygon(patched,pts,viewport)
            assert im.getbbox() is None,(pts,im.getbbox())
            outside+=1
        im,_=render_polygon(patched,[(-900,-900),(900,-900),(900,900),(-900,900)],viewport)
        expected=Image.new('L',(320,200));ImageDraw.Draw(expected).rectangle(viewport,fill=255)
        assert im.tobytes()==expected.tobytes();covered+=1
        # The sky/ground horizon is an intentionally open line. It must keep
        # filling down to the viewport bottom, including a banked camera.
        for y0,y1 in ((50,50),(25,140),(140,25),(t-20,b+20),(b+20,t-20)):
            results=[]
            for game in (original,patched):
                u=setup(game,viewport)
                call(u,0xcd68,regs={UC_M68K_REG_D0:2})
                edge=clip_edge(u,[(l-500,y0),(r+500,y1)],viewport)
                if edge[0]&0x80:continue
                call(u,0xccb6,stop=old(0xccd6),regs={UC_M68K_REG_A4:EDGE})
                results.append(bytes(u.mem_read(SCREEN,32000)))
            assert len(results)==2 and results[0]==results[1],('horizon',viewport,y0,y1)
            horizon_count+=1
        # An edge rejected behind the camera must not reuse the previous
        # object's cached boundary crossings in this record.
        u=setup(patched,viewport)
        clip_edge(u,[(l-100,t-20),(r+100,b+20)],viewport)
        assert r16(u,EDGE+8)
        call(u,0xc708,stop=old(0xc6d4),regs={UC_M68K_REG_A4:EDGE})
        assert r16(u,EDGE)==0x8080 and r16(u,EDGE+8)==0
        call(u,0xb250,regs={UC_M68K_REG_A4:EDGE});call(u,0xb3d6)
        assert not any(u.mem_read(SCREEN,32000))
        for _ in range(100):
            cx,cy=rng.randrange(-300,600),rng.randrange(-200,400)
            rx,ry=rng.randrange(30,700),rng.randrange(20,500)
            angle=rng.random()*math.tau;n=rng.choice((3,4,5,6,8))
            pts=[(round(cx+rx*math.cos(angle+k*math.tau/n)),round(cy+ry*math.sin(angle+k*math.tau/n))) for k in range(n)]
            im,_=render_polygon(patched,pts,viewport)
            expected=reference_polygon(pts,viewport)
            # Independent geometric clipping. The original integer scanline
            # rasterizer may differ by up to two pixels along sloping edges.
            outer=expected.filter(ImageFilter.MaxFilter(5))
            inner=expected.filter(ImageFilter.MinFilter(5))
            assert ImageChops.subtract(im,outer).getbbox() is None,('extra pixels',viewport,pts)
            assert ImageChops.subtract(inner,im).getbbox() is None,('missing pixels',viewport,pts)
            shape_count+=1
    return dict(all_passed=True,vertical_tail_reproductions=2,unchanged_inside_polygons=inside,
                wholly_outside_polygons=outside,full_viewport_polygons=covered,
                independent_geometry_cases=shape_count,unchanged_line_clipping_cases=line_count,
                unchanged_horizon_cases=horizon_count,near_plane_reuse_cases=len(VIEWPORTS),
                user_mode_compatibility=user_mode,
                viewports=VIEWPORTS,scope='Real 68000 line clipping, scanline accumulation and planar polygon fill; no whole-game emulator run.')


if __name__=='__main__':
    path=Path(sys.argv[1]) if len(sys.argv)>1 else WORK/'ZoomF3_test.adf'
    report=verify(game_from_adf(SOURCE.read_bytes()),game_from_adf(path.read_bytes()))
    write_json(WORK/'clip_edges_tests.json',report)
    print(report)
