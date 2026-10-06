"""Unit tests for illustrate.py. No API calls, no cost.

Run with: python -m unittest
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import illustrate as il


class ComposePromptTests(unittest.TestCase):
    def test_append_style(self):
        self.assertEqual(il.compose_prompt("一只猫", "扁平矢量"), "一只猫，扁平矢量")

    def test_style_already_present(self):
        self.assertEqual(il.compose_prompt("扁平矢量的猫", "扁平矢量"), "扁平矢量的猫")

    def test_no_style(self):
        self.assertEqual(il.compose_prompt("一只猫", None), "一只猫")

    def test_empty_content_uses_style(self):
        self.assertEqual(il.compose_prompt("", "风格"), "风格")


class SanitizeIdTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(il.sanitize_id("s3_arch"), "s3_arch")

    def test_illegal_and_spaces(self):
        self.assertEqual(il.sanitize_id("a b/c:d?e"), "a_b_c_d_e")

    def test_empty_default(self):
        self.assertEqual(il.sanitize_id(""), "img")


class ItemPlanTests(unittest.TestCase):
    def test_flash_1_5k(self):
        self.assertEqual(il.item_plan("flash", "1.5K", None), ("5.0-flash", "1.5K", 0.12))

    def test_pro_2k(self):
        self.assertEqual(il.item_plan("pro", "2K", None), ("5.0-pro", "2K", 0.60))

    def test_16_9_stays_1_5k(self):
        # 2048x1152 = 2.36M pixels -> 1.5K tier, not 2K.
        _, tier, cost = il.item_plan("flash", "1.5K", "16:9")
        self.assertEqual((tier, cost), ("1.5K", 0.12))

    def test_unknown_model_has_no_price(self):
        _, _, cost = il.item_plan("foo", "1.5K", None)
        self.assertIsNone(cost)


class ResolveTests(unittest.TestCase):
    def test_resolve_fills_image_and_keeps_existing(self):
        with tempfile.TemporaryDirectory() as d:
            spec = {"slides": [
                {"title": "a", "image_id": "x1"},
                {"title": "b", "image": "keep.png"},
                {"title": "c", "image_id": "missing"},
            ]}
            res = {"items": [{"id": "x1", "path": "out/x1.jpg", "ok": True}]}
            sp, rp, op = Path(d) / "spec.json", Path(d) / "res.json", Path(d) / "out.json"
            sp.write_text(json.dumps(spec), encoding="utf-8")
            rp.write_text(json.dumps(res), encoding="utf-8")

            il.run_resolve(str(sp), str(rp), str(op))

            got = json.loads(op.read_text(encoding="utf-8"))
            self.assertEqual(got["slides"][0]["image"], "out/x1.jpg")
            self.assertEqual(got["slides"][1]["image"], "keep.png")   # untouched
            self.assertNotIn("image", got["slides"][2])               # missing -> no image


if __name__ == "__main__":
    unittest.main()
