"""GitVersion release numbers are embedded without modifying the repository."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.build import build

ROOT = Path(__file__).resolve().parents[1]


class GitVersionPackageTests(unittest.TestCase):
    def test_embed_numeric_version_for_both_channels(self):
        source = ROOT / 'Ejix/Ejix.manifest'
        original = source.read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            for channel in ('release', 'prerelease'):
                archive, checksum = build(output=temp, kind='addin', channel=channel,
                                          version_override='9.8.7')
                self.assertTrue(checksum.is_file())
                with zipfile.ZipFile(archive) as zipped:
                    self.assertEqual(json.loads(zipped.read('Ejix/Ejix.manifest'))['version'], '9.8.7')
        self.assertEqual(source.read_bytes(), original)
