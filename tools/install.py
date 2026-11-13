#!/usr/bin/env python3
"""Copy the bundled skill into a host's skills directory without overwriting."""
import argparse
import os
from pathlib import Path
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=('codex', 'claude-code'), default='codex')
    parser.add_argument('--skills-dir', type=Path, help='Custom host skills directory')
    args = parser.parse_args()
    if args.skills_dir:
        root = args.skills_dir.expanduser().resolve()
    elif args.host == 'codex':
        root = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'skills'
    else:
        root = Path.home() / '.claude' / 'skills'
    target = root / 'video-understanding'
    source = Path(__file__).resolve().parents[1] / 'skills' / 'video-understanding'
    try:
        # lexists also catches dangling symlinks; copytree refuses existing targets.
        if os.path.lexists(target):
            raise FileExistsError(f'Already exists: {target}. Review or back it up before reinstalling.')
        if not (source / 'SKILL.md').is_file():
            raise FileNotFoundError('Bundled SKILL.md missing; run from a complete checkout.')
        shutil.copytree(source, target)
    except OSError as error:
        print(f'Installation failed: {error}', file=sys.stderr)
        return 1
    print(f'Installed: {target}')
    print('Install runtime dependencies using references/setup.md; reload the host skill catalog if needed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
