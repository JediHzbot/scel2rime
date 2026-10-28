"""Renderer tests: header, row shape, weight scaling, deduplication, naming."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import builders
from scel2rime import rime, scel


def parse_render(text: str) -> tuple[dict[str, str], list[list[str]]]:
    """Split rendered output into the YAML header map and the data rows."""
    head, _, body = text.partition("...\n")
    header = {}
    for line in head.splitlines():
        if not line or line.startswith("#") or line.startswith("---") or line.startswith("  - "):
            continue
        if ": " in line:
            key, value = line.split(": ", 1)
            header[key.strip()] = value.strip()
    rows = [line.split("\t") for line in body.strip().splitlines() if line.strip()]
    return header, rows


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.dictionary = scel.parse(
            builders.build_new(
                [
                    ("宕机", ["dang", "ji"], 1),
                    ("信息系统", ["xin", "xi", "xi", "tong"], 10),
                    ("冗余", ["rong", "yu"], 2),
                ],
                name="测试词库",
            ),
            "测试词库.scel",
        )

    def test_header_is_valid_rime_dictionary_syntax(self):
        header, rows = parse_render(rime.render(self.dictionary, "测试词库"))
        self.assertEqual(header["name"], "测试词库")
        self.assertEqual(header["version"], '"1"')
        self.assertEqual(header["sort"], "by_weight")
        self.assertEqual(header["use_preset_vocabulary"], "true")
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(len(row), 3)

    def test_rows_are_sorted_by_weight(self):
        _header, rows = parse_render(rime.render(self.dictionary, "d"))
        weights = [int(row[2]) for row in rows]
        self.assertEqual(weights, sorted(weights, reverse=True))
        self.assertEqual(rows[0][0], "信息系统")

    def test_weight_scaling(self):
        _h, rows = parse_render(rime.render(self.dictionary, "d", scale=1))
        weights = {row[0]: int(row[2]) for row in rows}
        self.assertEqual(weights["宕机"], 1)
        self.assertEqual(weights["信息系统"], 10)

        _h, rows = parse_render(rime.render(self.dictionary, "d", scale=1000))
        weights = {row[0]: int(row[2]) for row in rows}
        self.assertEqual(weights["宕机"], 1000)

    def test_original_order_is_preserved_when_asked(self):
        _h, rows = parse_render(rime.render(self.dictionary, "d", sort_by_weight=False))
        self.assertEqual([row[0] for row in rows], ["宕机", "信息系统", "冗余"])

    def test_duplicates_collapse_to_highest_grade(self):
        dictionary = scel.parse(
            builders.build_new(
                [("冗余", ["rong", "yu"], 2), ("冗余", ["rong", "yu"], 8), ("冗余", ["rong", "yu"], 5)]
            ),
            "dup.scel",
        )
        _h, rows = parse_render(rime.render(dictionary, "d", scale=1))
        self.assertEqual(rows, [["冗余", "rong yu", "8"]])


class NamingTests(unittest.TestCase):
    def test_name_prefers_dictionary_name(self):
        dictionary = scel.parse(builders.build_new([("词", ["ci"], 1)], name="我的词库"), "file.scel")
        self.assertEqual(rime.name_for(dictionary), "我的词库")

    def test_name_falls_back_to_stem_then_digest(self):
        dictionary = scel.parse(builders.build_new([("词", ["ci"], 1)], name=""), "plain.scel")
        self.assertEqual(rime.name_for(dictionary), "plain")

        anonymous = scel.parse(builders.build_new([("词", ["ci"], 1)], name="词库"), "词库.scel")
        self.assertEqual(rime.name_for(anonymous), "词库")

    def test_path_hostile_characters_are_replaced(self):
        self.assertEqual(rime.sanitize_name(' a/b:c*d?e"f<g>h|i '), "a_b_c_d_e_f_g_h_i")
        self.assertEqual(rime.sanitize_name("   "), "sogou_dict")

    def test_override_wins(self):
        dictionary = scel.parse(builders.build_new([("词", ["ci"], 1)], name="原名"), "file.scel")
        self.assertEqual(rime.name_for(dictionary, override="custom"), "custom")


if __name__ == "__main__":
    unittest.main()
