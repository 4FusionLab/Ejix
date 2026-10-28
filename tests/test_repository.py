# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / 'Ejix/Ejix.manifest').read_text(encoding='utf-8'))['version']
spec = importlib.util.spec_from_file_location('check_ejix', ROOT / 'scripts/check_project.py')
project = importlib.util.module_from_spec(spec)
spec.loader.exec_module(project)


class RepositoryTests(unittest.TestCase):
    def test_documentation_pairs_links_and_release_tag(self):
        self.assertEqual(project.check(tag='v' + VERSION), VERSION)

    def test_mismatched_tag_rejected(self):
        with self.assertRaisesRegex(ValueError, 'tag must match'):
            project.check(tag='v9.9.9')

    def test_pending_evidence_blocks_stable_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.fixture(root)
            record['cad']['macos']['status'] = 'pending'
            self.save(root, record)
            with self.assertRaisesRegex(ValueError, 'native CAD acceptance'):
                project.check_acceptance(root, VERSION)

    def test_link_checker_finds_missing_local_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'README.md').write_text('[Broken](docs/missing.md)\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Broken local documentation'):
                project.check_links(root)

    def test_banner_is_self_contained_accessible_svg(self):
        tree = ET.parse(ROOT / 'docs/assets/ejix-banner.svg')
        ns = {'svg': 'http://www.w3.org/2000/svg'}
        self.assertIsNotNone(tree.find('svg:title', ns))
        self.assertIsNotNone(tree.find('svg:desc', ns))
        self.assertFalse(tree.findall('.//svg:script', ns))
        self.assertFalse(tree.findall('.//svg:image', ns))

    def fixture(self, root):
        shutil.copytree(ROOT / 'Ejix', root / 'Ejix', ignore=shutil.ignore_patterns('__pycache__'))
        (root / 'release').mkdir()
        (root / 'report.md').write_text('Synthetic test evidence only.\n', encoding='utf-8')
        return {'schema': 1, 'version': VERSION, 'source_sha256': project.source_digest(root),
                'cad': {name: {'status': 'passed', 'fusion': 'test-build', 'os': 'test-os', 'report': 'report.md'}
                        for name in ('macos', 'windows')},
                'custom_feature_api': {'resolution': 'preview-api-removed', 'report': 'report.md'}}

    def save(self, root, record):
        (root / 'release/acceptance.json').write_text(json.dumps(record), encoding='utf-8')

    def test_stable_gate_accepts_complete_matching_synthetic_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.save(root, self.fixture(root))
            project.check_acceptance(root, VERSION)

    def test_runtime_change_invalidates_earlier_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.save(root, self.fixture(root))
            with (root / 'Ejix/__init__.py').open('a', encoding='utf-8') as file:
                file.write('\n# changed runtime\n')
            with self.assertRaisesRegex(ValueError, 'current runtime'):
                project.check_acceptance(root, VERSION)

    def test_preview_api_resolution_is_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.fixture(root)
            record['custom_feature_api']['resolution'] = None
            self.save(root, record)
            with self.assertRaisesRegex(ValueError, 'Preview API'):
                project.check_acceptance(root, VERSION)

    def test_explicit_limitations_policy_allows_documented_partial_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.fixture(root)
            record['release_policy'] = 'limitations-accepted'
            record['cad']['macos']['status'] = 'partial'
            record['cad']['windows'].update(status='not-tested', fusion=None, os=None)
            record['custom_feature_api']['resolution'] = 'preview-risk-accepted'
            self.save(root, record)
            project.check_acceptance(root, VERSION)
            del record['release_policy']
            self.save(root, record)
            with self.assertRaisesRegex(ValueError, 'native CAD acceptance'):
                project.check_acceptance(root, VERSION)

    def test_preview_risk_requires_explicit_limitations_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.fixture(root)
            record['custom_feature_api']['resolution'] = 'preview-risk-accepted'
            self.save(root, record)
            with self.assertRaisesRegex(ValueError, 'Preview API'):
                project.check_acceptance(root, VERSION)

    def test_evidence_report_must_exist_inside_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self.fixture(root)
            record['cad']['windows']['report'] = '../outside.md'
            self.save(root, record)
            with self.assertRaisesRegex(ValueError, 'CAD evidence report'):
                project.check_acceptance(root, VERSION)

    def test_source_digest_normalizes_text_line_endings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'Ejix').mkdir()
            file = root / 'Ejix/A.py'
            file.write_bytes(b'one\ntwo\n')
            lf = project.source_digest(root)
            file.write_bytes(b'one\r\ntwo\r\n')
            self.assertEqual(lf, project.source_digest(root))
