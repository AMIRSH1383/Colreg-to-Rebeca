"""Synchronize OpenCode's portable copy from canonical agents/ instructions."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check without writing')
    args = parser.parse_args()
    source = ROOT / 'agents/colreg_extractor.md'
    target = ROOT / '.opencode/agents/colreg_extractor.md'
    if args.check:
        raise SystemExit(0 if target.exists() and source.read_bytes() == target.read_bytes() else 1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


if __name__ == '__main__':
    main()
