"""Parser tests. No third-party dictionary is stored in the repository."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import builders
from scel2rime import scel

SAMPLE_ENTRIES = [
    ("宕机", ["dang", "ji"], 1),
    ("抖动", ["dou", "dong"], 5),
    ("公务网", ["gong", "wu", "wang"], 9),
    ("绿", ["lv"], 7),
    ("女", ["nv"], 3),
    ("x86", ["x", "86"], 2),
]


class NewContainerTests(unittest.TestCase):
    def test_roundtrip_of_every_field(self):
        data = builders.build_new(
            SAMPLE_ENTRIES,
            name="测试词库",
            category="计算机",
            description="仅用于单元测试",
        )
        parsed = scel.parse(data, "测试.scel")

        self.assertEqual(parsed.format_generation, "new")
        self.assertEqual(parsed.name, "测试词库")
        self.assertEqual(parsed.category, "计算机")
        self.assertEqual(parsed.description, "仅用于单元测试")
        self.assertEqual(len(parsed.entries), len(SAMPLE_ENTRIES))
        self.assertEqual(parsed.warnings, [])

        by_word = {entry.word: entry for entry in parsed.entries}
        self.assertEqual(by_word["宕机"].syllables, ("dang", "ji"))
        self.assertEqual(by_word["公务网"].pinyin, "gong wu wang")
        self.assertEqual(by_word["绿"].syllables, ("lv",))
        self.assertEqual(by_word["女"].syllables, ("nv",))
        self.assertEqual(by_word["x86"].frequency, 2)

    def test_empty_dictionary(self):
        parsed = scel.parse(builders.build_new([]), "empty.scel")
        self.assertEqual(parsed.entries, [])
        self.assertEqual(parsed.warnings, [])

    def test_unicode_and_long_words(self):
        entries = [("𠮷野家", ["ji", "ye", "jia"], 4), ("a" * 40, ["a"], 1)]
        parsed = scel.parse(builders.build_new(entries), "long.scel")
        self.assertEqual(parsed.entries[0].word, "𠮷野家")
        self.assertEqual(parsed.entries[1].word, "a" * 40)

    def test_many_entries(self):
        entries = [(f"词{i}", ["ci", "yu"], i % 10 + 1) for i in range(5000)]
        parsed = scel.parse(builders.build_new(entries), "big.scel")
        self.assertEqual(len(parsed.entries), 5000)
        self.assertEqual(parsed.warnings, [])

    def test_large_conversion_stays_linear(self):
        # 20k rows ~ a mid-size downloaded dictionary. Guards the parser against
        # accidental O(n^2) behaviour as dictionaries grow.
        import time

        entries = [(f"词条{i}", ["ci", "tiao", "yu"], i % 10 + 1) for i in range(20000)]
        data = builders.build_new(entries, name="大词库")
        started = time.perf_counter()
        parsed = scel.parse(data, "large.scel")
        elapsed = time.perf_counter() - started
        self.assertEqual(len(parsed.entries), 20000)
        self.assertEqual(parsed.warnings, [])
        self.assertLess(elapsed, 10.0, f"parsing 20k entries took {elapsed:.1f}s")

    def test_truncated_entry_stream_reports_instead_of_raising(self):
        data = builders.build_new(SAMPLE_ENTRIES)
        truncated = data[:-30]  # header intact, tail of the entry stream missing
        parsed = scel.parse(truncated, "cut.scel")
        self.assertGreater(len(parsed.warnings), 0)
        self.assertLess(len(parsed.entries), len(SAMPLE_ENTRIES))

    def test_file_shorter_than_header_is_rejected(self):
        data = builders.build_new(SAMPLE_ENTRIES)
        with self.assertRaises(scel.ScelError):
            scel.parse(data[:0x800], "tiny.scel")

    def test_bundled_ecs_container_is_refused(self):
        data = builders.build_new(SAMPLE_ENTRIES, magic=b"ECS\x01")
        with self.assertRaises(scel.ScelError) as caught:
            scel.parse(data, "bundled.scel")
        self.assertIn("ECS", str(caught.exception))

    def test_bad_header_is_rejected(self):
        with self.assertRaises(scel.ScelError):
            scel.parse(b"\x00" * 4, "tiny.scel")
        with self.assertRaises(scel.ScelError):
            scel.parse(b"\xff" * 32, "junk.scel")


class OldContainerTests(unittest.TestCase):
    def test_old_generation_roundtrip(self):
        data = builders.build_old(SAMPLE_ENTRIES)
        parsed = scel.parse(data, "old.scel")
        self.assertEqual(parsed.format_generation, "old")
        self.assertEqual(len(parsed.entries), len(SAMPLE_ENTRIES))
        self.assertEqual(parsed.entries[0].word, "宕机")
        self.assertEqual(parsed.entries[0].syllables, ("dang", "ji"))
        self.assertTrue(any("metadata" in warning for warning in parsed.warnings))


if __name__ == "__main__":
    unittest.main()
