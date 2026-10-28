# SPDX-License-Identifier: GPL-3.0-only
"""Check repository metadata, documentation links and stable-release evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ('README', 'CONTRIBUTING', 'SUPPORT', 'SECURITY', 'CODE_OF_CONDUCT', 'CHANGELOG',
         'docs/INSTALLATION', 'docs/GUIDE', 'docs/ARCHITECTURE', 'docs/UX',
         'docs/VALIDATION', 'docs/PUBLISHING')


def source_digest(root=ROOT):
    digest = hashlib.sha256()
    for path in sorted((Path(root) / 'Ejix').rglob('*'), key=lambda p: p.relative_to(root).as_posix()):
        if '__pycache__' in path.parts or path.suffix not in ('.py', '.manifest', '.svg', '.png'):
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError('Runtime source must be a regular file: ' + str(path))
        data = path.read_bytes()
        if path.suffix != '.png':
            data = data.replace(b'\r\n', b'\n')
        digest.update(path.relative_to(root).as_posix().encode('utf-8') + b'\0')
        digest.update(str(len(data)).encode('ascii') + b'\0' + data)
    return digest.hexdigest()


def check_links(root=ROOT):
    errors = []
    documents = [*Path(root).glob('*.md'), *(Path(root) / 'docs').rglob('*.md'),
                 *(Path(root) / '.github').rglob('*.md')]
    for path in documents:
        content = re.sub(r'```.*?```', '', path.read_text(encoding='utf-8'), flags=re.S)
        links = re.findall(r'!?\[[^\]\n]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)', content)
        links += re.findall(r'(?:href|src)="([^"]+)"', content)
        for link in links:
            parsed = urlsplit(link.strip('<>'))
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (path.parent / unquote(parsed.path)).resolve()
            if not target.is_relative_to(Path(root).resolve()) or not target.exists():
                errors.append(str(path.relative_to(root)) + ': ' + link)
    if errors:
        raise ValueError('Broken local documentation links:\n' + '\n'.join(errors))


def check(root=ROOT, tag=None, stable=False):
    root = Path(root).resolve()
    required = ['LICENSE', 'NOTICE', '.github/pull_request_template.md', '.github/ISSUE_TEMPLATE/config.yml',
                '.github/workflows/ci.yml', '.github/workflows/release.yml', '.github/dependabot.yml',
                'docs/assets/ejix-banner.svg', 'release/acceptance.json']
    required += [name + suffix for name in PAIRS for suffix in ('.md', '.ru.md')]
    for name in required:
        if not (root / name).is_file():
            raise ValueError('Missing project file: ' + name)
    manifest = json.loads((root / 'Ejix/Ejix.manifest').read_text(encoding='utf-8'))
    version = manifest['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Manifest version must be MAJOR.MINOR.PATCH.')
    if manifest.get('author') != '4FusionLab' or manifest.get('type') != 'addin':
        raise ValueError('Unexpected manifest author or add-in type.')
    if tag is not None and tag != 'v' + version:
        raise ValueError('Release tag must match manifest: v' + version)
    for path in (root / 'Ejix').glob('*.py'):
        if not path.read_text(encoding='utf-8').startswith('# SPDX-License-Identifier: GPL-3.0-only'):
            raise ValueError('Missing runtime license header: ' + path.name)
    check_links(root)
    if tag:
        for suffix in ('.md', '.ru.md'):
            if not (root / 'docs/releases' / (version + suffix)).is_file():
                raise ValueError('Missing release notes: ' + version + suffix)
    if stable:
        check_acceptance(root, version)
    return version


def check_acceptance(root, version):
    root = Path(root).resolve()
    record = json.loads((root / 'release/acceptance.json').read_text(encoding='utf-8'))
    if record.get('schema') != 1 or record.get('version') != version:
        raise ValueError('Stable release requires matching acceptance metadata.')
    if record.get('source_sha256') != source_digest(root):
        raise ValueError('Stable release requires CAD evidence for the current runtime source digest.')
    policy = record.get('release_policy', 'full-acceptance')
    if policy not in ('full-acceptance', 'limitations-accepted'):
        raise ValueError('Unknown stable release evidence policy.')
    limitations_accepted = policy == 'limitations-accepted'
    for platform in ('macos', 'windows'):
        evidence = record.get('cad', {}).get(platform, {})
        status = evidence.get('status')
        if status != 'passed' and not (limitations_accepted and status in ('partial', 'not-tested')):
            raise ValueError('Stable release requires native CAD acceptance: ' + platform)
        if status in ('passed', 'partial') and (not evidence.get('fusion') or not evidence.get('os')):
            raise ValueError('Stable release requires native CAD environment details: ' + platform)
        report = evidence.get('report')
        path = (root / report).resolve() if isinstance(report, str) and report else None
        if not path or not path.is_relative_to(root) or not path.is_file() or not path.read_text(encoding='utf-8').strip():
            raise ValueError('Missing CAD evidence report: ' + platform)
    api = record.get('custom_feature_api', {})
    accepted = ('preview-api-removed', 'api-released-by-autodesk')
    if limitations_accepted:
        accepted += ('preview-risk-accepted',)
    if api.get('resolution') not in accepted:
        raise ValueError('Resolve Custom Feature Preview API before stable release.')
    report = api.get('report')
    path = (root / report).resolve() if isinstance(report, str) and report else None
    if not path or not path.is_relative_to(root) or not path.is_file() or not path.read_text(encoding='utf-8').strip():
        raise ValueError('Missing Custom Feature API release decision report.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag')
    parser.add_argument('--stable', action='store_true')
    parser.add_argument('--print-source-digest', action='store_true')
    args = parser.parse_args()
    if args.print_source_digest:
        print(source_digest())
    else:
        try:
            version = check(tag=args.tag, stable=args.stable)
        except ValueError as error:
            parser.exit(1, 'Project check failed: ' + str(error) + '\n')
        print('Project metadata and links OK; version ' + version)
