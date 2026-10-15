"""Check ST source validation with saved rosters and unexpected game changes."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.build_st import SOURCE,validate_source
from src.st_disk import STDisk


def main():
    source=SOURCE.read_bytes()
    validate_source(source)
    disk=STDisk(source)
    roster=disk.entry('ROSTER.TNK')
    changed=bytearray(source)
    changed[disk.cluster_offset(roster.cluster)+50]^=1
    changed[roster.offset+22:roster.offset+26]=b'\x12\x34\x56\x78'
    assert validate_source(bytes(changed))[1]
    for offset in (disk.cluster_offset(disk.entry('GAME.PRG').cluster)+100,100,roster.offset+28):
        changed=bytearray(source)
        changed[offset]^=1
        try:validate_source(bytes(changed))
        except AssertionError:pass
        else:raise AssertionError(f'Unexpected source modification accepted at {offset:x}')
    assert SOURCE.read_bytes()==source
    print('Saved roster accepted; modified program, boot and roster layout rejected.')


if __name__=='__main__':main()
