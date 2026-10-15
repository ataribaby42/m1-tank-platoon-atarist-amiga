"""Compile the shared editable PNGs to Atari ST interleaved screen words."""
from pathlib import Path
from hashlib import sha256
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import build_assets as common
from src.build_common import ART, WORK, write_json

ST_WORK = WORK / 'st'


def compile_assets(art=ART):
    original, _, manifest = common.compile_assets(art)
    raw = bytearray(original)
    for y in range(192):
        for word in range(20):
            for plane in range(4):
                src = plane*7680+y*40+word*2
                dst = y*160+word*8+plane*2
                raw[dst:dst+2] = original[src:src+2]
    for name, size in common.SPRITES:
        offset = manifest['offsets'][name.upper()]
        table = offset + ((4+size[0]*size[1]+1) & ~1)
        count = struct.unpack_from('>H', raw, table+4)[0]
        for n in range(count):
            p = table+6+n*14
            old = struct.unpack_from('>H', raw, p)[0]
            struct.pack_into('>H', raw, p, (old//40)*160+(old%40)*4)
    packed = common.lzpack(raw)
    assert common.lzunpack(packed) == raw
    manifest.update(platform='Atari ST', screen_format='4 interleaved big-endian plane words per 16 pixels',
                    raw_sha256=sha256(raw).hexdigest(), packed_sha256=sha256(packed).hexdigest(), packed_bytes=len(packed))
    return bytes(raw), packed, manifest


def build(art=ART, work=ST_WORK):
    raw, packed, manifest = compile_assets(art)
    work.mkdir(parents=True, exist_ok=True)
    (work/'zoom_art.bin').write_bytes(packed)
    (work/'zoom_art_raw.bin').write_bytes(raw)
    (work/'zoom_art.i').write_text(''.join(f'ART_{n} equ {v}\n' for n,v in manifest['offsets'].items())
                                 + f'ART_SIZE equ {len(raw)}\n', encoding='ascii')
    write_json(work/'zoom_art_manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    build()
