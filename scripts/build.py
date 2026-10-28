# SPDX-License-Identifier: GPL-3.0-only
"""Deterministic source archive. Does not install or connect to Fusion."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def source_files(root):
    paths = {root / name for name in ('.gitignore', '.gitattributes', '.editorconfig', 'LICENSE', 'NOTICE')}
    paths.update(root.glob('*.md'))
    for directory, patterns in {
        'Ejix': ('*.py', '*.manifest', '*.png', '*.svg'), 'scripts': ('*.py',),
        'tests': ('*.py',), 'docs': ('*.md', '*.svg', '*.png'), '.github': ('*.yml', '*.md'),
        'release': ('*.json', '*.md'),
    }.items():
        for pattern in patterns:
            paths.update((root / directory).rglob(pattern))
    def public_file(path):
        relative = path.relative_to(root)
        if '__pycache__' in path.parts or relative.as_posix() == 'PLAN.md':
            return False
        if relative.parts[:2] == ('docs', 'validation'):
            return False
        if relative.as_posix() in ('docs/releases/0.1.0.md', 'docs/releases/0.1.0.ru.md'):
            return False
        if relative.as_posix() == '.github/ISSUE_TEMPLATE/03-cad-validation.yml':
            return False
        return not (relative.parts[:2] == ('docs', 'assets') and path.name.startswith('icon-family-'))
    return sorted((p for p in paths if public_file(p)),
                  key=lambda p: p.relative_to(root).as_posix())


def build(root=ROOT, output=None, kind='source', channel='prototype'):
    root = Path(root).resolve()
    manifest = json.loads((root / 'Ejix/Ejix.manifest').read_text(encoding='utf-8'))
    version = manifest['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Manifest version must be MAJOR.MINOR.PATCH.')
    if kind not in ('source', 'addin') or channel not in ('prototype', 'prerelease', 'release'):
        raise ValueError('Unknown package kind or channel.')
    output = Path(output) if output else root / 'dist'
    output.mkdir(parents=True, exist_ok=True)
    suffixes = {('source', 'prototype'): '-prototype', ('addin', 'prototype'): '-addin-prototype',
                ('source', 'prerelease'): '-source-prerelease', ('addin', 'prerelease'): '-prerelease',
                ('source', 'release'): '-source', ('addin', 'release'): ''}
    archive = output / ('Ejix-' + version + suffixes[kind, channel] + '.zip')
    files = source_files(root)
    if kind == 'addin':
        files = [p for p in files if p.relative_to(root).parts[0] in ('Ejix', 'docs')
                 or p.parent == root and (p.suffix == '.md' or p.name in ('LICENSE', 'NOTICE'))]
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as zipped:
        for path in files:
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
                raise ValueError('Package source must be a regular repository file: ' + str(path))
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            content = path.read_bytes()
            if path.suffix != '.png':
                content = content.replace(b'\r\n', b'\n')
            zipped.writestr(info, content)
    checksum = archive.with_suffix('.zip.sha256')
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n', encoding='ascii')
    return archive, checksum


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--kind', choices=('source', 'addin'), default='source')
    parser.add_argument('--channel', choices=('prototype', 'prerelease', 'release'), default='prototype')
    args = parser.parse_args()
    for path in build(output=args.output, kind=args.kind, channel=args.channel):
        print(path)
