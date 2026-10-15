"""Build the complete mod: colors, lead, clipping, thermal, laser, Mi-24 and Shift+F3."""
from pathlib import Path
from hashlib import sha256
import copy
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.build_common import ART, WORK, assembler, publish_adf, run_tool, write_json
from src.build_dark_green import build_adf, open_adf, snapshot, FSString
from src import build_assets

from src.hunk_executable import read_hunks, serialize

def patch_adf(source, patch_blob, asset_manifest):
    dev,vol=open_adf(source)
    before=snapshot(vol)
    original=bytes(vol.read_file(FSString('game')))
    vol.close();dev.close()
    header,ss=read_hunks(original)
    previous=copy.deepcopy(ss)
    mh,ms=read_hunks(patch_blob)
    assert [s['type'] for s in ms]==[1001,1003,1003,1003,1003]
    assert [s['size'] for s in ms[1:4]]==[ss[i]['size'] for i in (0,27,4)]
    remap={0:32,1:0,2:27,3:4,4:33}
    ext=copy.deepcopy(ms[0])
    ext['reloc']={remap[t]:offs for t,offs in ext['reloc'].items()}
    ss.extend([ext,copy.deepcopy(ms[4])])
    header['hunks'].extend([dict(size=s['size'],memf='') for s in ss[32:]])
    names=['frame_begin','frame_end','key_handler','click_handler','sliders',
           'reset_view','zoom_enabled','saved_flags','backup0','backup1',
           'render_begin','render_hud','project_axis','project_horizon','scale_long',
           'native_scene','viewport_save',
           'draw_sight','draw_range','draw_art','unpack_art','art_raw','hud_active','panel_begin',
           'laser_acquire']
    exported=dict(zip(names,struct.unpack_from('>'+str(len(names))+'I',ext['data'])))
    assert all(exported[n]<ss[32]['size'] for n in names[:6])
    hooks=[]
    def hook(address,name,length,expected,call=False):
        off=address-0x9c
        assert ss[0]['data'][off:off+length].hex()==expected
        code=bytearray(ss[0]['data'])
        opcode=b'\x4e\xb9' if call or name=='frame_end' else b'\x4e\xf9'
        code[off:off+length]=opcode+struct.pack('>I',exported[name])+b'\x4e\x71'*((length-6)//2)
        ss[0]['data']=bytes(code)
        for t in ss[0]['reloc']:
            ss[0]['reloc'][t]=[p for p in ss[0]['reloc'][t] if not off<=p<off+length]
        ss[0]['reloc'].setdefault(32,[]).append(off+2)
        hooks.append(dict(file_offset=hex(address),function=name,length=length))
    hook(0x323a,'laser_acquire',6,'302a023c6a08')
    hook(0x8288,'frame_begin',6,'20390001b466')
    hook(0x830a,'panel_begin',10,'302a00c46b12536a00c4')
    hook(0x83b2,'frame_end',6,'4eb900005d48')
    hook(0x8fe8,'key_handler',8,'0c7900080001abc0')
    hook(0x8608,'click_handler',8,'302a00be0c400006')
    hook(0x8486,'sliders',6,'4a790001e8d8')
    hook(0x8244,'reset_view',6,'357c000400be')
    hook(0x8388,'render_begin',10,'610002f44eb90000be74')
    hook(0x83a2,'render_hud',8,'61001b6a610016da')
    hook(0xc8a8,'project_axis',6,'48c0e7a081c2',call=True)
    hook(0xc8c8,'project_axis',6,'48c0e7a081c2',call=True)
    hook(0xcbec,'project_horizon',6,'81c2d06a020c',call=True)
    hook(0x9c40,'draw_sight',6,'4eb900001e3e',call=True)
    hook(0x9bb0,'draw_range',6,'4eb900002056',call=True)
    key_offset=0x80+0x52
    data=bytearray(ss[3]['data']);assert data[key_offset]==0
    data[key_offset]=0xfd;ss[3]['data']=bytes(data)
    game=serialize(header,ss)
    rh,rs=read_hunks(game)
    assert len(rs)==34 and rh['hunks']==header['hunks']
    for i in range(34):
        assert rs[i].get('data')==ss[i].get('data')
        assert {t:sorted(o) for t,o in rs[i]['reloc'].items()}=={
            t:sorted(o) for t,o in ss[i]['reloc'].items() if o}
    for i in range(32):
        if i not in (0,3):
            assert previous[i].get('data')==ss[i].get('data')
            assert previous[i]['reloc']==ss[i]['reloc']
    dev,vol=open_adf(source,False)
    node=vol.get_file_path_name(FSString('game'));meta=node.get_meta_info()
    node.delete(update_ts=False)
    vol.root_dir.create_file(FSString('game'),game,meta_info=meta,update_ts=False)
    vol.close();adf=bytes(dev.data);dev.close()
    dev,vol=open_adf(adf);after=snapshot(vol);vol.close();dev.close()
    assert before.keys()==after.keys()
    assert [k for k in before if before[k]!=after[k]]==['game']
    assert adf[:1024]==source[:1024] and len(adf)==901120
    report=dict(hooks=hooks,exports=exported,hunks=34,extra_runtime_bytes=sum(s['size'] for s in ss[32:]),
                game_sha256=sha256(game).hexdigest(),adf_sha256=sha256(adf).hexdigest(),
                unchanged_other_files=True,green_vehicle_patch_preserved=True,
                crop=[56,0,200,120],destination=[0,0,320,192],status_rows=[192,199],
                native_3d_viewport=[64,10,257,187],native_3d_pixels=True,
                projection_scale=[8,5],cockpit_and_hud_from_editable_png=True,
                cockpit_cached_per_buffer=True,smoke_redrawn_only_on_state_change=True,
                hud_sparse_planar_drawing=True,
                f3_zoom_toggle_preserves_target_both_directions=True,
                laser_rejects_invalid_range_lock=True,laser_lock_range_metres=[200,7998],
                laser_fix_applies_to_normal_and_zoom_f3=True,
                asset_manifest=asset_manifest)
    return game, adf, report


def build():
    # Resolve dependencies afresh; no extracted file, previous output ADF,
    # debugger dump or precompiled patch is an input to this build.
    vasm = assembler()
    print('Compiling PNG assets from gfx...')
    manifest = build_assets.build()
    print('Building dark green vehicle materials from the original ADF...')
    source, green_report = build_adf()
    write_json(WORK / 'base_fixes.verification.json', green_report)
    dev, vol = open_adf(source)
    _, source_hunks = read_hunks(bytes(vol.read_file(FSString('game'))))
    vol.close(); dev.close()
    (WORK / 'original_hunks.i').write_text(''.join(
        f'ORIGINAL_HUNK_{i}_SIZE equ ${source_hunks[i]["size"]:x}\n' for i in (0,27,4)))
    print('Assembling the Shift+F3 patch...')
    run_tool([vasm, '-m68000', '-Fhunkexe', '-nosym',
              '-L', WORK / 'zoom_f3.lst', '-o', WORK / 'zoom_f3.hunk',
              ROOT / 'src/zoom_f3.s'], 'assembler.log')
    game, adf, report = patch_adf(source, (WORK / 'zoom_f3.hunk').read_bytes(), manifest)
    (WORK / 'ZoomF3_game').write_bytes(game)
    (WORK / 'ZoomF3_test.adf').write_bytes(adf)
    write_json(WORK / 'zoom_f3_build.json', report)
    print('Verifying 68000 execution, target preservation and disk integrity...')
    run_tool([sys.executable, ROOT / 'src/test_zoom_f3.py'], 'processor_tests.log')
    from src.test_lead import verify_adf
    report['lead_fix_tests'] = verify_adf(adf)
    from src.test_clip_edges import verify as verify_clip_edges
    from src.test_lead import game_from_adf
    from src.build_common import SOURCE
    report['clip_edges_fix_tests'] = verify_clip_edges(game_from_adf(SOURCE.read_bytes()),game)
    report['clip_edges_fix'] = green_report['clip_edges_fix']
    from src.test_thermal import verify as verify_thermal
    report['thermal_fix'] = green_report['thermal_fix']
    report['thermal_fix_tests'] = verify_thermal(game_from_adf(SOURCE.read_bytes()),game)
    from src.test_mi24 import verify as verify_mi24
    report['mi24_fix'] = green_report['mi24_fix']
    report['mi24_fix_tests'] = verify_mi24(game_from_adf(SOURCE.read_bytes()),game,'amiga')
    write_json(WORK / 'mi24_tests.json', report['mi24_fix_tests'])
    write_json(WORK / 'zoom_f3_build.json', report)
    tests = json.loads((WORK / 'zoom_f3_tests.json').read_text(encoding='utf-8'))
    assert tests['all_passed']
    run_tool([sys.executable, '-m', 'amitools.tools.xdfscan', '-v',
              WORK / 'ZoomF3_test.adf'], 'adf_scan.log')
    for name, digest in manifest['input_sha256'].items():
        assert sha256((ART / name).read_bytes()).hexdigest() == digest, f'PNG changed during build: {name}'
    verification = {'build': report, 'processor_tests': tests,
                    'adf_filesystem_scan': 'passed', 'full_game_emulator_test': False,
                    'game_in_adf_matches_working_copy': True,
                    'original_adf_sha256': green_report['source_adf_sha256']}
    write_json(WORK / 'M1TankPlatoon_modded.verification.json', verification)
    destination = publish_adf('M1TankPlatoon_modded.adf', adf)
    print(f'Built and verified: {destination}')
    return destination


def main():
    build()

if __name__=='__main__':main()
