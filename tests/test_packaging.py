"""Regression for the metadata encoding that previously blocked pip installation."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

class PackageMetadataTests(unittest.TestCase):
    def test_project_metadata_is_utf8_without_bom_and_matches_runtime(self):
        raw = (ROOT / "pyproject.toml").read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "TOML must not start with a UTF-8 BOM")
        text = raw.decode("utf-8")
        try:
            import tomllib
        except ImportError:  # Python 3.10 has no stdlib TOML reader.
            version = re.search(r'^version = "([^"]+)"', text, re.MULTILINE).group(1)
        else:
            version = tomllib.loads(text)["project"]["version"]
        runtime = (ROOT / "src/scel2rime/__init__.py").read_text("utf-8-sig")
        self.assertEqual(version, re.search(r'^__version__ = "([^"]+)"', runtime, re.MULTILINE).group(1))

if __name__ == "__main__":
    unittest.main()
