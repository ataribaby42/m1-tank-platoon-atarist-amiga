"""Compile editable PNGs into the native 4-plane cockpit and indexed HUD sprites.

Reads gfx only. Never regenerates, rescales or overwrites an editable PNG.
Atlas frames are excluded from the game data.
"""
from hashlib import sha256
from pathlib import Path
import argparse
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.build_common import ART, WORK, write_json
from PIL import Image

COLORS = [0x000, 0x00a, 0x090, 0x0aa, 0xa00, 0x444, 0xa50, 0xaaa,
          0x666, 0x55f, 0x5d5, 0x5ff, 0xf55, 0xf5f, 0xff5, 0xfff]
RGB = [tuple(((n >> shift) & 15) * 17 for shift in (8, 4, 0)) for n in COLORS]
PALETTE = sum((list(c) for c in RGB), []) + [0, 0, 0] * (256 - 16)
FONT_NAMES = [*'0123456789', 'hvezdicka']
ATLASES = {
    'font_atlas': {'size': (165, 14), 'fields': {
        'font_' + c: (1 + i * 15, 1, 13, 12) for i, c in enumerate(FONT_NAMES)}},
    'smoke1_atlas': {'size': (56, 36), 'fields': {
        'smoke1_prepinac_0': (1, 1, 26, 20), 'smoke1_prepinac_1': (29, 1, 26, 20),
        'smoke1_svetlo_0': (1, 23, 26, 12), 'smoke1_svetlo_1': (29, 23, 26, 12)}},
}
SPRITES = [('zamerovac_normal', (103, 38)), ('zamerovac_thermal', (103, 38)),
           ('smoke1_prepinac_0', (26, 20)), ('smoke1_prepinac_1', (26, 20)),
           ('smoke1_svetlo_0', (26, 12)), ('smoke1_svetlo_1', (26, 12))]
SPRITES += [('font_' + c, (13, 12)) for c in FONT_NAMES]
INPUTS = ['kokpit.png', 'zamerovac_normal.png', 'zamerovac_thermal.png',
          'font_atlas.png', 'smoke1_atlas.png', 'paleta.png']


def indexed(width, height, data):
    image = Image.frombytes('P', (width, height), bytes(data))
    image.putpalette(PALETTE)
    image.info['transparency'] = 16
    return image


def validate(path, size, box=None):
    with Image.open(path) as source:
        image = source.convert('RGBA')
    if box is not None:
        image = image.crop(box)
    if image.size != size:
        raise ValueError(f'{path.name}: expected {size}, found {image.size}')
    pixels = []
    for i, rgba in enumerate(image.get_flattened_data()):
        if rgba[3] == 0:
            pixels.append(16)
        elif rgba[3] == 255 and rgba[:3] in RGB:
            pixels.append(RGB.index(rgba[:3]))
        else:
            x, y = i % size[0], i // size[0]
            if box is not None:
                x += box[0]
                y += box[1]
            raise ValueError(f'{path.name}: pixel ({x},{y}) {rgba} is outside the palette '
                             'or partly transparent; disable antialiasing')
    return indexed(*size, pixels)


def asset(name, size, art=ART):
    for atlas, layout in ATLASES.items():
        if name in layout['fields']:
            x, y, width, height = layout['fields'][name]
            assert (width, height) == size
            path = art / (atlas + '.png')
            with Image.open(path) as image:
                if image.size != layout['size']:
                    raise ValueError(f'{path.name}: expected {layout["size"]}, found {image.size}')
            return validate(path, size, (x, y, x + width, y + height))
    return validate(art / (name + '.png'), size)


def encode_plane(image):
    width, height = image.size
    data = bytearray(width * height // 8 * 4)
    for y in range(height):
        for x in range(width):
            color = image.getpixel((x, y))
            color = 0 if color == 16 else color
            for plane in range(4):
                if color & (1 << plane):
                    data[plane * width * height // 8 + y * width // 8 + x // 8] |= 1 << (7 - x % 8)
    return bytes(data)


def lzpack(data):
    """Format shared with unpack_art in zoom_f3.s, including overlapping copies."""
    from collections import defaultdict, deque
    data = bytes(data)
    found = defaultdict(lambda: deque(maxlen=64))
    output = bytearray()
    literal = bytearray()
    i = 0

    def flush():
        if literal:
            output.append(len(literal) - 1)
            output.extend(literal)
            literal.clear()

    while i < len(data):
        key = data[i:i + 3]
        best = offset = 0
        for position in reversed(found[key]):
            if i - position > 65535:
                break
            length = 3
            while length < 130 and i + length < len(data) and data[position + length] == data[i + length]:
                length += 1
            if length > best:
                best, offset = length, i - position
            if length == 130:
                break
        if best >= 4:
            flush()
            output.append(128 + best - 3)
            output.extend(struct.pack('>H', offset))
            length = best
        else:
            literal.append(data[i])
            length = 1
            if len(literal) == 128:
                flush()
        for position in range(i, i + length):
            found[data[position:position + 3]].append(position)
        i += length
    flush()
    return bytes(output)


def lzunpack(data):
    output = bytearray()
    i = 0
    while i < len(data):
        token = data[i]
        i += 1
        if token < 128:
            length = token + 1
            assert i + length <= len(data)
            output.extend(data[i:i + length])
            i += length
        else:
            offset = struct.unpack_from('>H', data, i)[0]
            i += 2
            assert 0 < offset <= len(output)
            for _ in range((token & 127) + 3):
                output.append(output[-offset])
    return bytes(output)


def encode_sprite(image, visible_width=None):
    """Indexed clipping fallback followed by sparse 16-pixel planar blocks.

    Each record is offset, opacity, white-pixel mask, four plane words.
    Runtime shifts words for arbitrary X positions; transparent blocks vanish.
    White has its own mask so distance warnings retain the original pen color.
    """
    width, height = image.size
    output = bytearray(struct.pack('>HH', width, height) + image.tobytes())
    if len(output) & 1:
        output.append(16)
    clipped_width = width if visible_width is None else visible_width
    records = bytearray()
    for y in range(height):
        for word in range((clipped_width + 15) // 16):
            mask = white = 0
            planes = [0] * 4
            for bit in range(16):
                x = word * 16 + bit
                if x >= clipped_width:
                    continue
                color = image.getpixel((x, y))
                if color == 16:
                    continue
                pixel = 0x8000 >> bit
                mask |= pixel
                if color == 15:
                    white |= pixel
                for plane in range(4):
                    if color & (1 << plane):
                        planes[plane] |= pixel
            if mask:
                records.extend(struct.pack('>7H', y * 40 + word * 2, mask, white, *planes))
    output.extend(struct.pack('>HHH', clipped_width, height, len(records) // 14))
    output.extend(records)
    return output


def compile_assets(art=ART):
    """Validate all inputs before writing any generated file."""
    for name in INPUTS:
        if not (art / name).is_file():
            raise FileNotFoundError(f'Missing editable PNG: {art / name}')
    palette = validate(art / 'paleta.png', (16, 1))
    if palette.tobytes() != bytes(range(16)):
        raise ValueError('paleta.png must contain the original 16 game colors in order')
    background = asset('kokpit', (320, 200), art)
    for box in ((64, 10, 258, 188), (0, 192, 320, 200)):
        if any(pixel != 16 for pixel in background.crop(box).tobytes()):
            raise ValueError('kokpit.png: keep the 3D viewport and bottom status rows transparent')
    raw = bytearray(encode_plane(background.crop((0, 0, 320, 192))))
    offsets = {'COCKPIT': 0}
    for name, size in SPRITES:
        if len(raw) & 1:
            raw.append(16)
        offsets[name.upper()] = len(raw)
        image = asset(name, size, art)
        visible_width = 11 if 'prepinac' in name else 8 if 'svetlo' in name else None
        raw.extend(encode_sprite(image, visible_width))
    packed = lzpack(raw)
    assert lzunpack(packed) == raw, 'Compressed graphics failed verification'
    manifest = {
        'pixel_scale': '1:1', 'cockpit': [320, 200], 'viewport': [64, 10, 257, 187],
        'status_rows': [192, 199], 'palette_rgb': RGB, 'transparent_index': 16,
        'sprites': dict(SPRITES), 'offsets': offsets, 'decoded_bytes': len(raw), 'packed_bytes': len(packed),
        'sprite_encoding': 'indexed fallback + sparse 16-pixel planar blocks',
        'atlases': ATLASES, 'atlas_fields_format': 'x,y,width,height; zero-based; border excluded',
        'positions': {'smoke1_prepinac': [309, 34], 'smoke1_svetlo': [312, 13],
                      'zamerovac': [112, 79], 'vzdalenost': [96, 132]},
        'input_sha256': {name: sha256((art / name).read_bytes()).hexdigest() for name in INPUTS},
        'raw_sha256': sha256(raw).hexdigest(), 'packed_sha256': sha256(packed).hexdigest(),
    }
    return bytes(raw), packed, manifest


def build(art=ART, work=WORK):
    raw, packed, manifest = compile_assets(art)
    work.mkdir(parents=True, exist_ok=True)
    (work / 'zoom_art.bin').write_bytes(packed)
    (work / 'zoom_art_raw.bin').write_bytes(raw)
    (work / 'zoom_art.i').write_text(
        '\n'.join(f'ART_{name} equ {offset}' for name, offset in manifest['offsets'].items())
        + f'\nART_SIZE equ {len(raw)}\n', encoding='ascii')
    write_json(work / 'zoom_art_manifest.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gfx', type=Path, default=ART, help='Input PNG directory (default: project gfx)')
    parser.add_argument('--work', type=Path, default=WORK, help='Generated files directory (default: analysis/build)')
    args = parser.parse_args()
    manifest = build(args.gfx, args.work)
    print(f'Graphics verified: {manifest["decoded_bytes"]} raw bytes, {manifest["packed_bytes"]} compressed bytes')
    print(f'Generated files: {args.work.resolve()}')


if __name__ == '__main__':
    main()
