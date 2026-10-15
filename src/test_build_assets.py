"""Check that editable atlases reach the game and invalid PNGs fail safely."""
from hashlib import sha256
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.build_assets import ART, RGB, build, compile_assets, lzunpack
from PIL import Image


class AssetBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.art = self.root / 'gfx'
        self.work = self.root / 'build'
        shutil.copytree(ART, self.art)

    def change_pixel(self, name, position, color):
        path = self.art / name
        with Image.open(path) as source:
            image = source.convert('RGBA')
        image.putpixel(position, color)
        image.save(path)

    def test_atlas_edits_reach_game_and_borders_are_excluded(self):
        original, _, manifest = compile_assets(self.art)
        # Unpaletted annotation pixels are valid outside the extracted cells.
        self.change_pixel('font_atlas.png', (0, 0), (1, 2, 3, 255))
        self.change_pixel('smoke1_atlas.png', (0, 0), (4, 5, 6, 128))
        unchanged, _, _ = compile_assets(self.art)
        self.assertEqual(unchanged, original)
        self.change_pixel('font_atlas.png', (1, 1), (*RGB[2], 255))
        self.change_pixel('smoke1_atlas.png', (1, 1), (*RGB[3], 255))
        changed, packed, changed_manifest = compile_assets(self.art)
        for name,color in [('FONT_0',2),('SMOKE1_PREPINAC_0',3)]:
            self.assertEqual(changed[changed_manifest['offsets'][name]+4],color)
        # Extra sparse planar records can change offsets and lengths too.
        for name in manifest['offsets']:
            if name in ('FONT_0','SMOKE1_PREPINAC_0','COCKPIT'):
                continue
            size=manifest['sprites'][name.lower()]
            length=4+size[0]*size[1]
            a=manifest['offsets'][name];b=changed_manifest['offsets'][name]
            self.assertEqual(original[a:a+length],changed[b:b+length])
        self.assertNotEqual(changed, original)
        self.assertEqual(lzunpack(packed), changed)

    def test_invalid_png_leaves_previous_build_and_inputs_intact(self):
        inputs = {p.name: p.read_bytes() for p in self.art.iterdir() if p.is_file()}
        build(self.art, self.work)
        self.assertEqual(inputs, {p.name: p.read_bytes() for p in self.art.iterdir() if p.is_file()})
        outputs = {p.name: sha256(p.read_bytes()).digest() for p in self.work.iterdir()}
        self.change_pixel('font_atlas.png', (1, 1), (1, 2, 3, 255))
        with self.assertRaisesRegex(ValueError, 'font_atlas.png: pixel'):
            build(self.art, self.work)
        self.assertEqual(outputs, {p.name: sha256(p.read_bytes()).digest() for p in self.work.iterdir()})

    def test_partial_alpha_wrong_size_and_missing_atlas_are_rejected(self):
        path = self.art / 'font_atlas.png'
        original = path.read_bytes()
        self.change_pixel('font_atlas.png', (1, 1), (*RGB[15], 128))
        with self.assertRaisesRegex(ValueError, 'partly transparent'):
            compile_assets(self.art)
        path.write_bytes(original)
        with Image.open(path) as image:
            wrong = image.crop((0, 0, 164, 14))
        wrong.save(path)
        with self.assertRaisesRegex(ValueError, 'expected'):
            compile_assets(self.art)
        path.unlink()
        with self.assertRaisesRegex(FileNotFoundError, 'font_atlas.png'):
            compile_assets(self.art)

    def test_cockpit_keeps_native_viewport_and_status_holes(self):
        for position in ((64, 10), (0, 192)):
            with self.subTest(position=position):
                self.change_pixel('kokpit.png', position, (*RGB[15], 255))
                with self.assertRaisesRegex(ValueError, 'viewport and bottom status'):
                    compile_assets(self.art)
                self.change_pixel('kokpit.png', position, (0, 0, 0, 0))


if __name__ == '__main__':
    unittest.main()
