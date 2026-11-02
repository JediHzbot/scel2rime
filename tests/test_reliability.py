"""Regression tests for loss, batch status, parser boundaries and atomic writes."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "src"), str(Path(__file__).resolve().parent)]
import builders
from scel2rime import cli, rime, scel

class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scel2rime-test-")
        self.root = Path(self.temp.name)
        self.data = builders.build_new([("甲", ["jia"], 1), ("乙", ["yi"], 2)], name="same")
        self.good = self.root / "good.scel"
        self.good.write_bytes(self.data)
        self.out = self.root / "out"

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def convert(self, *inputs, extra=()):
        code, out, err = self.run_cli("convert", *map(str, inputs), "-o", str(self.out), "--json", *extra)
        self.assertFalse(err)
        return code, json.loads(out)

    def test_unknown_magic_rejected(self):
        with self.assertRaises(scel.ScelError):
            scel.parse(self.data[:4] + b"BAD!" + self.data[8:])

    def test_all_truncation_offsets_never_leak_struct_error(self):
        for builder in (builders.build_new, builders.build_old):
            data = builder([("甲", ["jia"], 1), ("乙", ["yi"], 2)])
            for end in range(len(data)):
                try:
                    result = scel.parse(data[:end])
                    # Whole-entry boundaries can be syntactically valid. No claimed source count exists.
                    self.assertLess(len(result.entries), 2)
                except scel.ScelError:
                    pass

    def test_partial_default_refuses_output_but_continues_batch(self):
        bad = self.root / "bad.scel"
        bad.write_bytes(builders.build_new([("甲", ["jia"], 1), ("乙", ["yi"], 2)], name="bad")[:-17])
        code, report = self.convert(bad, self.good)
        self.assertEqual(code, 3)
        self.assertEqual(report["summary"], {"partial": 1, "converted": 1})
        self.assertFalse((self.out / "bad.dict.yaml").exists())
        self.assertTrue((self.out / "same.dict.yaml").exists())

    def test_partial_opt_in_never_reports_complete_success(self):
        self.good.write_bytes(self.data[:-1])
        code, report = self.convert(self.good, extra=("--allow-partial",))
        self.assertEqual(code, 3)
        self.assertEqual(report["written_files"], 1)
        self.assertFalse(report["results"][0]["complete"])

    def test_missing_input_is_failure(self):
        code, report = self.convert(self.good, self.root / "missing")
        self.assertEqual(code, 1)
        self.assertEqual(report["summary"], {"failed": 1, "converted": 1})

    def test_batch_collision_rejects_all_even_force(self):
        other = self.root / "other.scel"
        other.write_bytes(builders.build_new([("丙", ["bing"], 3)], name="SAME"))
        self.out.mkdir()
        sentinel = self.out / "same.dict.yaml"
        sentinel.write_bytes(b"ORIGINAL")
        code, report = self.convert(self.good, other, extra=("--force",))
        self.assertEqual(code, 1)
        self.assertEqual(report["summary"], {"conflict": 2})
        self.assertEqual(sentinel.read_bytes(), b"ORIGINAL")
        self.assertEqual(report["written_files"], 0)

    def test_dry_run_has_no_filesystem_effect(self):
        code, report = self.convert(self.good, extra=("--dry-run",))
        self.assertEqual(code, 0)
        self.assertEqual(report["summary"], {"planned": 1})
        self.assertFalse(self.out.exists())

    def test_write_failure_does_not_destroy_old_file(self):
        self.out.mkdir()
        dest = self.out / "same.dict.yaml"
        dest.write_bytes(b"ORIGINAL")
        with patch.object(rime.os, "replace", side_effect=PermissionError("locked")):
            code, report = self.convert(self.good, extra=("--force",))
        self.assertEqual(code, 1)
        self.assertEqual(report["summary"], {"failed": 1})
        self.assertEqual(dest.read_bytes(), b"ORIGINAL")
        self.assertEqual(list(self.out.iterdir()), [dest])

    def test_stdout_rejects_multiple_dictionaries(self):
        other = self.root / "other.scel"
        other.write_bytes(self.data)
        code, out, err = self.run_cli("convert", str(self.good), str(other), "--stdout")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertTrue(err)

    def test_old_metadata_warning_is_not_data_loss(self):
        self.good.write_bytes(builders.build_old([("甲", ["jia"], 1)]))
        code, report = self.convert(self.good)
        self.assertEqual(code, 0)
        self.assertTrue(report["results"][0]["warnings"])
        self.assertTrue(report["results"][0]["complete"])

    def test_ambiguous_yaml_names_are_quoted_and_devices_renamed(self):
        for name in ("true", "null", "123", "[a]", "#abc"):
            text = rime.render(scel.parse(self.data), name)
            self.assertIn("name: " + json.dumps(name, ensure_ascii=False), text)
        self.assertEqual(rime.sanitize_name("CON"), "dict_CON")

    def test_control_characters_not_written_as_dictionary_rows(self):
        parsed = scel.parse(builders.build_new([("a\tb", ["a"], 1)]))
        self.assertFalse(parsed.complete)
        self.assertEqual(parsed.entries, [])

    def test_scan_include_and_case_insensitive_extensions(self):
        self.good.rename(self.root / "GOOD.SCEL")
        with patch.object(cli, "SCAN_ROOTS", ()):
            code, out, _ = self.run_cli("scan", "--include", str(self.root), "--json")
        report = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(len(report["files"]), 1)
        self.assertEqual(report["searched_roots"], [str(self.root)])

if __name__ == "__main__":
    unittest.main()
