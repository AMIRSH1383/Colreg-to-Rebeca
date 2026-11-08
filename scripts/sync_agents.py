"""Synchronize OpenCode's portable copy from canonical agents/ instructions."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check without writing')
    args = parser.parse_args()
    for name in ('colreg_extractor', 'semantic_binding_agent'):
        source = ROOT / f'agents/{name}.md'
        target = ROOT / f'.opencode/agents/{name}.md'
        if args.check:
            if not target.exists() or source.read_bytes() != target.read_bytes():
                raise SystemExit(1)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())



if __name__ == '__main__':
    main()
