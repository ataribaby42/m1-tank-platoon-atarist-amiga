"""Install correct viewport-border polygon closure without changing projection."""
import copy
import struct
from src.build_common import ROOT,WORK,assembler,run_tool
from src.hunk_executable import read_hunks,serialize


def patch_game(game):
    run_tool([assembler(),'-m68000','-Fhunkexe','-nosym','-L',WORK/'clip_edges.lst',
              '-o',WORK/'clip_edges.hunk',ROOT/'src/clip_edges.s'],'clip_edges_assembler.log')
    header,segments=read_hunks(game)
    before=copy.deepcopy(segments)
    _,patch=read_hunks((WORK/'clip_edges.hunk').read_bytes())
    assert len(patch)==2 and [p['type'] for p in patch]==[1001,1003]
    extension=bytearray(patch[0]['data']);code=bytearray(segments[0]['data']);start=len(code)
    names=['clip_edge','polygon_edge','border_right','border_left','reject_edge','horizon_edge']
    exports={name:start+n for name,n in zip(names,struct.unpack_from('>6I',extension))}
    for target,offsets in patch[0]['reloc'].items():
        assert target in (0,1)
        for offset in offsets:
            if target==0:
                struct.pack_into('>I',extension,offset,struct.unpack_from('>I',extension,offset)[0]+start)
            segments[0]['reloc'].setdefault(0,[]).append(start+offset)
    hooks=[]
    for address,name,expected in ((0xcf04,'clip_edge','610001fc6612'),
                                  (0xb250,'polygon_edge','3014816a011a'),
                                  (0xb442,'border_right','356a01160002'),
                                  (0xb462,'border_left','356a01120002'),
                                  (0xc708,'reject_edge','38bc808060c6'),
                                  (0xccc2,'horizon_edge','4eb90000b1b4')):
        off=address-0x9c
        assert code[off:off+6].hex()==expected,hex(address)
        overlaps=[(target,r) for target,offsets in before[0]['reloc'].items() for r in offsets if off<=r<off+6]
        assert overlaps==([(0,off+2)] if name=='horizon_edge' else [])
        for target,offsets in segments[0]['reloc'].items():
            segments[0]['reloc'][target]=[r for r in offsets if not off<=r<off+6]
        opcode=b'\x4e\xb9' if name=='horizon_edge' else b'\x4e\xf9'
        code[off:off+6]=opcode+struct.pack('>I',exports[name])
        segments[0]['reloc'].setdefault(0,[]).append(off+2)
        hooks.append(dict(original_file_offset=hex(address),function=name,before=expected))
    code.extend(extension)
    segments[0]['data']=bytes(code);segments[0]['size']=len(code);header['hunks'][0]['size']=len(code)
    result=serialize(header,segments)
    _,checked=read_hunks(result)
    assert len(checked)==len(before)
    for old,new in zip(before[1:],checked[1:]):
        assert old.get('data')==new.get('data') and old['size']==new['size']
        assert {k:sorted(v) for k,v in old['reloc'].items()}==new['reloc']
    return result,dict(hooks=hooks,added_code_bytes=len(extension),extra_bss_bytes=0,
                       condition_codes_saved_without_privileged_instructions=True,
                       original_projection_and_line_clipping_preserved=True,
                       original_polygon_rasterizer_preserved=True)
