# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / 'Ejix/Ejix.manifest').read_text(encoding='utf-8'))['version']
spec = importlib.util.spec_from_file_location('build_ejix', ROOT / 'scripts/build.py')
build_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_module)


class PackagingTests(unittest.TestCase):
    def test_release_package_contains_product_screenshots_without_working_notes(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build_module.build(ROOT, temp, kind='source', channel='release')
            with zipfile.ZipFile(archive) as packaged:
                names = set(packaged.namelist())
        self.assertIn('docs/images/eject-preview.png', names)
        self.assertIn('docs/images/eject-cut.png', names)
        self.assertIn('docs/images/eject-parts.png', names)
        self.assertNotIn('PLAN.md', names)
        self.assertFalse(any(name.startswith('docs/validation/') for name in names))

    def test_deterministic_archive_has_manifest_resources_and_no_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            first, checksum = build_module.build(output=Path(temp) / 'one')
            second, _ = build_module.build(output=Path(temp) / 'two')
            self.assertEqual(first.read_bytes(), second.read_bytes())
            digest = hashlib.sha256(first.read_bytes()).hexdigest()
            self.assertEqual(checksum.read_text(encoding='ascii').split()[0], digest)
            with zipfile.ZipFile(first) as archive:
                names = set(archive.namelist())
                for path in ('Ejix/Ejix.py', 'Ejix/Ejix.manifest', 'LICENSE', 'README.md', 'README.ru.md',
                             'Ejix/resources/eject/16x16.png', 'Ejix/resources/eject/32x32.png'):
                    self.assertIn(path, names)
                self.assertFalse(any('__pycache__' in name or name.startswith(('.git/', 'dist/')) for name in names))
                manifest = json.loads(archive.read('Ejix/Ejix.manifest'))
                self.assertEqual(manifest['author'], '4FusionLab')
                self.assertEqual(manifest['type'], 'addin')

    def test_addin_package_keeps_runtime_docs_and_license_without_dev_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build_module.build(output=temp, kind='addin')
            self.assertEqual(archive.name, 'Ejix-' + VERSION + '-addin-prototype.zip')
            with zipfile.ZipFile(archive) as zipped:
                names = set(zipped.namelist())
                for path in ('Ejix/Ejix.py', 'Ejix/feature.py', 'NOTICE', 'LICENSE',
                             'docs/assets/ejix-banner.svg', 'docs/INSTALLATION.md', 'docs/INSTALLATION.ru.md'):
                    self.assertIn(path, names)
                self.assertFalse(any(name.startswith(('tests/', 'scripts/', '.github/')) for name in names))

    def test_release_package_names_preserve_manifest_version(self):
        expected = {('source', 'release'): 'Ejix-' + VERSION + '-source.zip',
                    ('addin', 'release'): 'Ejix-' + VERSION + '.zip',
                    ('source', 'prerelease'): 'Ejix-' + VERSION + '-source-prerelease.zip',
                    ('addin', 'prerelease'): 'Ejix-' + VERSION + '-prerelease.zip'}
        with tempfile.TemporaryDirectory() as temp:
            for (kind, channel), name in expected.items():
                archive, _ = build_module.build(output=temp, kind=kind, channel=channel)
                self.assertEqual(archive.name, name)

    def test_all_python_sources_are_utf8(self):
        for path in ROOT.rglob('*.py'):
            if '__pycache__' not in path.parts:
                path.read_text(encoding='utf-8')
