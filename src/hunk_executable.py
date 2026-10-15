"""Read and serialize relocatable Amiga executables without losing hunk metadata."""
from io import BytesIO
import struct
from src import build_common
from amitools.binfmt.hunk.HunkReader import HunkReader

def read_hunks(data):
    r = HunkReader()
    assert r.read_file_obj('game', BytesIO(data)) == 0, r.error_string
    ss=[]
    for h in r.hunks:
        if h['type'] in (1001,1002,1003):
            ss.append(dict(h, reloc={}))
        elif h['type'] in (1004,1020):
            ss[-1]['reloc'].update(h['reloc'])
        else:
            assert h['type'] in (1011,1010), h['type']
    return r.hunks[0],ss

def serialize(header, ss):
    pack=lambda *n: struct.pack('>'+str(len(n))+'I',*n)
    out=bytearray(pack(1011,0,len(ss),0,len(ss)-1))
    for alloc in header['hunks']:
        flag={'':0,'chip':0x40000000,'fast':0x80000000}[alloc['memf']]
        out.extend(pack(flag|alloc['size']//4))
    for s in ss:
        flag={'':0,'chip':0x40000000,'fast':0x80000000}[s['memf']]
        out.extend(pack(flag|s['type'],s['size']//4))
        if s['type']!=1003:
            assert len(s['data'])==s['size']
            out.extend(s['data'])
        if s['reloc']:
            out.extend(pack(1004))
            for target,offsets in sorted(s['reloc'].items()):
                if offsets: out.extend(pack(len(offsets),target,*sorted(offsets)))
            out.extend(pack(0))
        out.extend(pack(1010))
    return bytes(out)

