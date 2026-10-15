"""Rebuild in an empty workspace, then test PNG updates and failure isolation."""
from hashlib import sha256
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.build_common import ROOT, SOURCE, ART, WORK, assembler, write_json
from src.build_assets import RGB
from PIL import Image


def main():
    # Copy inputs only; no generated files or earlier ADF outputs are available.
    parent = (ROOT / 'analysis').resolve()
    parent.mkdir(exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix='build-check-', dir=parent)
    project = Path(temporary.name).resolve()
    assert project.parent == parent and project != parent
    try:
        shutil.copytree(ROOT / 'src', project / 'src', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ART, project / 'gfx')
        (project / 'assets').mkdir()
        shutil.copy2(SOURCE, project / 'assets/M1TankPlatoon.adf')
        (project / '.tools').mkdir()
        shutil.copy2(assembler(), project / '.tools' / assembler().name)
        environment = os.environ.copy()
        environment['PYTHONPATH'] = str(ROOT / '.tools/python') + os.pathsep + environment.get('PYTHONPATH', '')

        def run(script, success=True):
            result = subprocess.run([sys.executable, project / 'src' / script],
                                    cwd=parent, env=environment,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            assert (result.returncode == 0) == success, result.stdout.decode('utf-8', 'replace')

        def outputs():
            files = list((project / 'output').iterdir())
            assert all(p.suffix == '.adf' for p in files)
            return {p.name: sha256(p.read_bytes()).hexdigest() for p in files}

        def graphics():
            return {p.name: p.read_bytes() for p in (project / 'gfx').iterdir() if p.is_file()}

        original_graphics = graphics()
        run('build_all.py')
        original = outputs()
        assert set(original) == {'M1TankPlatoon_modded.adf'}
        assert graphics() == original_graphics
        # Each builder can run independently from outside the project.
        run('build_dark_green.py')
        run('build_zoom_f3.py')
        assert outputs() == original
        assert graphics() == original_graphics
        atlas = project / 'gfx/font_atlas.png'
        with Image.open(atlas) as source:
            image = source.convert('RGBA')
        old = image.getpixel((1, 1))
        image.putpixel((1, 1), (*RGB[2 if old != (*RGB[2], 255) else 3], 255))
        image.save(atlas)
        run('build_zoom_f3.py')
        changed = outputs()
        assert changed['M1TankPlatoon_modded.adf'] != original['M1TankPlatoon_modded.adf']
        image.putpixel((1, 1), (1, 2, 3, 128))
        image.save(atlas)
        run('build_zoom_f3.py', success=False)
        assert outputs() == changed, 'Invalid graphics replaced a successful ADF'
        assert (project / 'assets/M1TankPlatoon.adf').read_bytes() == SOURCE.read_bytes()
        write_json(WORK / 'pipeline_tests.json', {
            'all_passed': True, 'clean_build_sha256': original,
            'checks': ['Clean input-only workspace, launched outside the project',
                       'Standalone and combined builds produce identical ADFs',
                       'Editable PNGs and original ADF remain untouched',
                       'Font atlas edit changes the complete modded ADF',
                       'Invalid PNG leaves the final ADF intact', 'Only M1TankPlatoon_modded.adf in output']})
    finally:
        # The resolved temporary directory was checked against the workspace
        # before cleanup. It contains copies only, never links to user inputs.
        temporary.cleanup()
    print('Build pipeline verified from clean inputs; PNG update and failure checks passed.')


if __name__ == '__main__':
    main()
