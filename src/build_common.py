"""Project paths, tool execution and final ADF publication."""
from hashlib import sha256
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets/M1TankPlatoon.adf'
ART = ROOT / 'gfx'
WORK = ROOT / 'analysis/build'
OUTPUT = ROOT / 'output'
sys.path.insert(0, str(ROOT / '.tools/python'))
if not __debug__:
    raise RuntimeError('Build verification requires Python without -O or -OO.')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def run_tool(arguments, log_name):
    WORK.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(ROOT / '.tools/python') + os.pathsep + environment.get('PYTHONPATH', '')
    result = subprocess.run([str(a) for a in arguments], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment)
    log = WORK / log_name
    log.write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(f'Tool failed; see {log}\n' + result.stdout.decode('utf-8', 'replace'))
    return result.stdout.decode('utf-8', 'replace')


def assembler():
    local = ROOT / '.tools' / ('vasmm68k_mot.exe' if os.name == 'nt' else 'vasmm68k_mot')
    if local.is_file():
        return local
    found = shutil.which('vasmm68k_mot')
    if found:
        return Path(found)
    raise FileNotFoundError(f'Missing Motorola 68000 assembler: {local}')


def publish_adf(name, data):
    """Only replace the final disk after every build check has succeeded."""
    assert Path(name).name == name and name.endswith('.adf')
    assert len(data) == 901120, 'Unexpected ADF size'
    WORK.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT / name
    with tempfile.NamedTemporaryFile(dir=WORK, suffix='.adf', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        os.replace(temporary, destination)
        assert sha256(destination.read_bytes()).digest() == sha256(data).digest()
    finally:
        temporary.unlink(missing_ok=True)
    return destination
