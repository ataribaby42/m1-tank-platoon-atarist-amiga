"""Build all completed Amiga modifications for the supplied Atari ST disk.

Inputs: original assets/M1 Tank Platoon.st, shared src patches and gfx PNGs.
Output: output/M1TankPlatoon_modded.st. Never modifies the source disk or PNGs.
"""
from pathlib import Path
from hashlib import sha256
import json
import os
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.build_common import ROOT, ART, OUTPUT, write_json
from src.build_st_assets import ST_WORK, build as build_assets
from src.st_disk import STDisk
from src.st_executable import TOSExecutable
from src.st_assembly import compile_patch

SOURCE = ROOT/'assets/M1 Tank Platoon.st'
SOURCE_SHA = '004347f9eedd028fbc1020f00464fbfb809fbffb0eeadbf7383ee3d1e0803c9c'
SOURCE_WITHOUT_ROSTER_SHA = '714a108ae5d896a717cf47734b3f35953b60400e63a3a7c18ccbc9af069661f5'
NAMES = {
 'mi24':['attack_helicopter_call'],
 'lead':['track_direction'],
 'clip_edges':['clip_edge','polygon_edge','border_right','border_left','reject_edge','horizon_edge'],
 'zoom_f3':['frame_begin','frame_end','key_handler','click_handler','sliders','reset_view',
            'zoom_enabled','saved_flags','backup0','backup1','render_begin','render_hud',
            'project_axis','project_horizon','scale_long','native_scene','viewport_save',
            'draw_sight','draw_range','draw_art','unpack_art','art_raw','hud_active','panel_begin','laser_acquire'],
}


def u16(data,p): return struct.unpack_from('>H',data,p)[0]
def u32(data,p): return struct.unpack_from('>I',data,p)[0]
def put32(data,p,v): struct.pack_into('>I',data,p,v)


def validate_source(source):
    """Accept the original image with only its saved crew roster changed.

    All other bytes, including GAME.PRG, boot, FATs and directory structure,
    remain protected by the normalized whole-image hash. Never change input.
    """
    digest=sha256(source).hexdigest()
    if digest==SOURCE_SHA:return digest,False
    disk=STDisk(source)
    roster=disk.entry('ROSTER.TNK')
    assert roster.size==4112 and disk.chain(roster.cluster)==[202,203,204,205,206], 'Unsupported ST roster layout'
    normalized=bytearray(source)
    for cluster in disk.chain(roster.cluster):
        p=disk.cluster_offset(cluster)
        normalized[p:p+disk.cluster_size]=bytes(disk.cluster_size)
    normalized[roster.offset+22:roster.offset+26]=bytes(4)  # DOS write time/date
    assert sha256(normalized).hexdigest()==SOURCE_WITHOUT_ROSTER_SHA, 'Unsupported Atari ST source disk'
    return digest,True


def colors(exe):
    data = exe.image
    before = bytes(data)
    def ptr(p):
        assert p in exe.relocations, hex(p)
        return u32(data,p)
    levels = {}
    for model in range(54):
        p=ptr(0x275e0+model*4); rows=[]
        for _ in range(8):
            rows.append(ptr(p+2))
            if u16(data,p)&0x8000: break
            p+=6
        else: raise AssertionError('Unterminated LOD list')
        levels[model]=rows
    targets=[m for m,rows in levels.items() if 0x1ad80 in rows]
    shapes={s for m in targets for s in levels[m]}
    other={s for m in levels if m not in targets for s in levels[m]}
    assert not shapes&other
    changes={}
    def material(p,new):
        assert before[p] in (4,6,12)
        changes[p]=new;data[p]=new
    for shape in shapes:
        kind=u16(data,shape+2)&255
        if kind==0: continue
        if kind==3:
            assert shape==0x1ad80 and u16(data,shape+4)==4
            material(shape+5,38); continue
        assert kind==1
        count=u16(data,shape+20)
        offsets,polygons=ptr(shape+22),ptr(shape+44)
        for face in range(count):
            start=polygons+before[offsets+face]
            if before[start] in (4,6,12): material(start,{4:35,6:36,12:37}[before[start]])
            p=start+1
            while before[p] not in (254,255):
                p+=1;assert p-start<256
            if before[p]==254:
                p+=1
                while before[p]!=255:
                    if before[p] in (4,6,12): material(p,{4:35,6:36,12:37}[before[p]])
                    p+=2;assert p-start<256
    extra=bytearray(); maps=[]
    for mode in range(6):
        old=bytes(data[ptr(0x3297c+4*mode):ptr(0x3297c+4*mode)+35])
        additions=[old[i] for i in (4,6,12,4)]
        if mode in (2,4,5): additions=[0x20,0x52,0x82,6]
        elif mode==3:
            assert additions==[0,0x80,0x40,0]
            additions[2]=0x20
        address=len(before)+len(extra)
        put32(data,0x3297c+4*mode,address)
        extra.extend(old+bytes(additions))
        maps.append(dict(mode=mode,address=address,original=old.hex(),additions=additions))
    extra.extend(bytes((-len(extra))%4))
    return extra, dict(models=targets,shapes=len(shapes),changes=len(changes),maps=maps,
                       original_materials_preserved=True,map_enemy_colors_preserved=True)


def patch_game(original):
    exe=TOSExecutable(original)
    assert exe.serialize()==original, 'TOS roundtrip differs'
    original_end=len(exe.image); original_bss=exe.bss_size
    extra,color_report=colors(exe)
    sections={name:compile_patch(name) for name in NAMES}
    starts={}
    for name, ss in sections.items():
        starts[name]=original_end+len(extra)
        extra.extend(ss[0]['data'])
    growth=len(extra)
    state_start=original_end+growth+original_bss
    exports={}; new_relocs=[]
    for name,ss in sections.items():
        start=starts[name]; local=start-original_end
        for target,offsets in ss[0]['reloc'].items():
            assert target in (0,1,2)
            for p in offsets:
                value=u32(extra,local+p)
                if target==0: value+=start
                elif target==1:
                    if value>=original_end: value+=growth
                else: value+=state_start
                put32(extra,local+p,value)
                new_relocs.append(start+p)
        exports.update({n:u32(extra,local+i*4) for i,n in enumerate(NAMES[name])})
    # Original DATA grows; adjust only pre-existing references to original BSS.
    # Material-table pointers intentionally point into the new data extension.
    for p in exe.relocations:
        value=u32(exe.image,p)
        if original_end<=value<0x80000000 and not 0x3297c<=p<0x32994:
            assert value<=original_end+original_bss, (hex(p),hex(value))
            put32(exe.image,p,value+growth)
    exe.image.extend(extra)
    exe.data_size+=growth
    exe.bss_size+=sections['zoom_f3'][2]['size']
    exe.relocations.extend(new_relocs)
    hooks=[]
    def replace(p,expected,value):
        expected=bytes.fromhex(expected)
        assert exe.image[p:p+len(expected)]==expected, (hex(p),exe.image[p:p+len(expected)].hex())
        assert len(expected)==len(value)
        exe.image[p:p+len(value)]=value
    def hook(p,name,expected,call=False):
        n=len(bytes.fromhex(expected))
        replace(p,expected,(b'\x4e\xb9' if call else b'\x4e\xf9')+struct.pack('>I',exports[name])+b'\x4e\x71'*((n-6)//2))
        exe.relocations=[r for r in exe.relocations if not p<=r<p+n]+[p+2]
        hooks.append(dict(address=p,function=name,length=n))
    hook(0x2c8a,'track_direction','6100017c2a734000',True)
    hook(0x3700,'attack_helicopter_call','0c730015406a664e')
    replace(0x2caa,'3b400066',bytes.fromhex('4e714e71'))
    replace(0x4d14,'61000b3c',bytes.fromhex('4e714e71'))
    replace(0x4d20,'61000b30',bytes.fromhex('4e714e71'))
    replace(0x5c7c,'7001',bytes.fromhex('7000'))
    for p,n,e,c in [
        (0xc5d6,'clip_edge','610001fc6612',False),
        (0xa908,'polygon_edge','3014816a011a',False),
        (0xaafa,'border_right','356a01160002',False),
        (0xab1a,'border_left','356a01120002',False),
        (0xbdd4,'reject_edge','38bc808060c6',False),
        (0xc390,'horizon_edge','4eb90000a908',True),
        (0x27ca,'laser_acquire','302a023c6a08',False),
        (0x7866,'frame_begin','203900027f8e',False),
        (0x78e8,'panel_begin','302a00c46b20536a00c4',False),
        (0x8670,'key_handler','0c79000800027730',False),
        (0x7c24,'click_handler','302a00beb07c0006',False),
        (0x7a98,'sliders','4a790002b476',False),
        (0x7822,'reset_view','357c000400be',False),
        (0x797e,'render_begin','6100031e4eb90000b5dc',False),
        (0x7998,'render_hud','61001c146100176c',False),
        (0xbf74,'project_axis','48c0e7a081c2',True),
        (0xbf94,'project_axis','48c0e7a081c2',True),
        (0xc2ba,'project_horizon','81c2d06a020c',True),
        (0x92c8,'draw_sight','4eb900000c42',True),
        (0x9238,'draw_range','4eb900001174',True),
    ]: hook(p,n,e,c)
    # TOS BIOS returns scan 0x56 for Shift+F3; plain F3 remains 0x3d.
    replace(0xdd42+0x56,'01',b'\xfd')
    result=exe.serialize(); checked=TOSExecutable(result)
    assert checked.serialize()==result and checked.image==exe.image
    for row in color_report['maps']:
        assert exe.image[row['address']:row['address']+35].hex()==row['original']
    return result,dict(exports=exports,hooks=hooks,colors=color_report,
                       mi24_call_in_fixed=True,enemy_friendly_radio_text_suppressed=True,
                       initialized_growth=growth,extra_bss=exe.bss_size-original_bss,
                       original_bss_start=original_end,original_bss_size=original_bss,
                       original_bss_shift=growth,game_sha256=sha256(result).hexdigest())


def build(publish=True):
    source=SOURCE.read_bytes()
    source_digest,saved_roster=validate_source(source)
    manifest=build_assets()
    disk=STDisk(source); original=disk.read('GAME.PRG')
    game,report=patch_game(original)
    disk.replace('GAME.PRG',game)
    assert disk.data[:disk.sector]==source[:disk.sector]
    checked=STDisk(bytes(disk.data))
    assert checked.snapshot()==disk.snapshot()
    (ST_WORK/'GAME.PRG').write_bytes(game)
    (ST_WORK/'M1TankPlatoon_test.st').write_bytes(disk.data)
    report.update(source_sha256=source_digest,saved_roster_variant=saved_roster,
                  asset_manifest=manifest,changed_files=['GAME.PRG'],
                  disk_sha256=sha256(disk.data).hexdigest())
    write_json(ST_WORK/'build.json',report)
    from src.test_st import verify
    report['tests']=verify(original,game,report)
    write_json(ST_WORK/'mi24_tests.json',report['tests']['mi24'])
    evidence=ST_WORK/'emulator_verification.json'
    report['full_game_emulator_test']=False
    if evidence.is_file():
        runtime=json.loads(evidence.read_text(encoding='utf-8'))
        if runtime.get('game_sha256')==sha256(game).hexdigest() and runtime.get('all_passed'):
            report['full_game_emulator_test']=True
            report['emulator']=runtime
    for name,digest in manifest['input_sha256'].items():
        assert sha256((ART/name).read_bytes()).hexdigest()==digest
    assert SOURCE.read_bytes()==source
    write_json(ST_WORK/'verification.json',report)
    if publish:
        OUTPUT.mkdir(exist_ok=True)
        staged=ST_WORK/'publish.st';staged.write_bytes(disk.data)
        destination=OUTPUT/'M1TankPlatoon_modded.st'
        os.replace(staged,destination)
        print(f'Built and verified: {destination}')
    return report


if __name__=='__main__':
    build()
