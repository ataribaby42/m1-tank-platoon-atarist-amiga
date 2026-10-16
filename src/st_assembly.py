"""Reuse shared 68000 algorithms, adapting only ST addresses and screen access.

Generated assembler remains in analysis/build/st. Platform-specific drawing
is maintained in st_video.s; the canonical gameplay fixes stay shared.
"""
import re
from src.build_common import ROOT, assembler, run_tool
from src.build_st_assets import ST_WORK
from src.st_addresses import CODE, DATA
from src.hunk_executable import read_hunks


def translated(text):
    for old, mapping, origin in [('old0',CODE,'9c'), ('old27',DATA,'1b2f4')]:
        text = re.sub(rf'{old}\+\$([0-9a-f]+)-\${origin}',
                      lambda m: f'original+${mapping[int(m[1],16)]:x}', text)
    return text


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def compile_patch(name):
    text = (ROOT/'src'/f'{name}.s').read_text()
    if name != 'zoom_f3':
        text = text[:text.index('        section original_code,bss')]
        text += '        section original,bss\noriginal: ds.l 1\n'
    else:
        text = text.replace('analysis/build/zoom_art', 'analysis/build/st/zoom_art')
        text = replace(text, '        include "analysis/build/original_hunks.i"\n', '')
        # Both ST screens are contiguous, interleaved 32KB buffers.
        text = replace(text, '''        moveq #3,d7
.plane:
        movea.l (a6)+,a1
        move.w #1919,d6
.copy:
        move.l (a0)+,(a1)+
        dbra d6,.copy
        dbra d7,.plane''', '''        move.w #7679,d6
.copy:
        move.l (a0)+,(a1)+
        dbra d6,.copy''')
        a = text.index('        movea.l a0,a5\n')
        b = text.index('        tst.w art_ready\n', a)
        text = text[:a]+'''        move.w #7679,d6
.save:
        move.l (a1)+,(a0)+
        dbra d6,.save
'''+text[b:]
        a = text.index('        moveq #3,d7\n.art_plane:')
        b = text.index('.smoke:\n', a)
        text = text[:a]+'''        move.w #7679,d6
.art_copy:
        move.l (a0)+,(a1)+
        dbra d6,.art_copy
'''+text[b:]
        a = text.index('        lea art_raw+13*40+38,a0')
        b = text.index('        move.w #0,sprite_tint', a)
        text = text[:a]+'''        lea art_raw+13*160+152,a0
        lea 13*160+152(a1),a1
        moveq #40,d6
.smoke_row:
        move.l (a0),(a1)
        move.l 4(a0),4(a1)
        lea 160(a0),a0
        lea 160(a1),a1
        dbra d6,.smoke_row
'''+text[b:]
        # Restore the software cursor before erasing the refreshed status row;
        # its saved background may itself still contain external VIEW text.
        text = replace(text, '.zoom_panel:\n', '''.zoom_panel:
        move.w 8(a2),d0
        jsr original+$cc3e
''')
        text = replace(text, '''        moveq #3,d7
.plane:
        movea.l (a6)+,a1
        lea 192*40(a1),a1
        moveq #79,d6
.clear:
        clr.l (a1)+
        dbra d6,.clear
        dbra d7,.plane''', '''        lea 192*160(a1),a1
        move.w #319,d6
.clear:
        clr.l (a1)+
        dbra d6,.clear''')
        a = text.index('draw_art:\n')
        b = text.index('unpack_art:\n', a)
        text = text[:a]+'        include "src/st_video.s"\n\n'+text[b:]
        a = text.index('; d0=bitmap index')
        b = text.index('key_handler:\n', a)
        text = text[:a]+text[b:]
        a = text.index('        section original_code,bss')
        b = text.index('        section zoom_state,bss', a)
        text = text[:a]+'        section original,bss\noriginal: ds.l 1\n'+text[b:]
    text = translated(text)
    assert not re.search(r'old(?:0|27|4)[+:]', text)
    path = ST_WORK/f'{name}.s'
    path.write_text(text, encoding='ascii')
    run_tool([assembler(), '-m68000', '-Fhunkexe', '-nosym', '-L', ST_WORK/f'{name}.lst',
              '-o', ST_WORK/f'{name}.hunk', path], f'st/{name}_assembler.log')
    return read_hunks((ST_WORK/f'{name}.hunk').read_bytes())[1]
