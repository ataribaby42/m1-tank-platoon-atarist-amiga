"""Build the complete mod for Amiga (default), Atari ST, or both platforms."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import build_zoom_f3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=('amiga', 'st', 'all'), default='amiga')
    args = parser.parse_args()
    if args.platform in ('amiga', 'all'):
        build_zoom_f3.main()
    if args.platform in ('st', 'all'):
        from src.build_st import build
        build()


if __name__ == '__main__':
    main()
