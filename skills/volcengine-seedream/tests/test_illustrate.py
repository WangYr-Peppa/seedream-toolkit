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


class ParsePlacementsTests(unittest.TestCase):
    def test_basic(self):
        data = {
            "placements": [
                {"slide": 1, "image": "a.png", "left": 0, "top": 0, "width": 10, "height": 5.625}
            ]
        }
        got = il.parse_placements(data)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["slide"], 1)
        self.assertEqual(got[0]["image"], "a.png")
        self.assertEqual(got[0]["left"], 0.0)
        self.assertEqual(got[0]["width"], 10.0)
        self.assertEqual(got[0]["height"], 5.625)
        self.assertFalse(got[0]["remove_pictures"])

    def test_defaults(self):
        data = {"placements": [{"slide": 2, "image": "b.png"}]}
        got = il.parse_placements(data)
        self.assertEqual(got[0]["slide"], 2)
        self.assertEqual(got[0]["left"], 0.0)
        self.assertEqual(got[0]["top"], 0.0)
        self.assertEqual(got[0]["width"], 1.0)
        self.assertEqual(got[0]["height"], 1.0)
        self.assertFalse(got[0]["remove_pictures"])

    def test_remove_pictures_true(self):
        data = {"placements": [{"slide": 1, "image": "b.png", "remove_pictures": True}]}
        got = il.parse_placements(data)
        self.assertTrue(got[0]["remove_pictures"])

    def test_invalid_slide_zero(self):
        data = {"placements": [{"slide": 0, "image": "a.png"}]}
        with self.assertRaisesRegex(ValueError, "slide"):
            il.parse_placements(data)

    def test_missing_image(self):
        data = {"placements": [{"slide": 1}]}
        with self.assertRaisesRegex(ValueError, "image"):
            il.parse_placements(data)

    def test_negative_dimension(self):
        data = {"placements": [{"slide": 1, "image": "a.png", "width": -1}]}
        with self.assertRaisesRegex(ValueError, "width"):
            il.parse_placements(data)

    def test_not_a_list(self):
        data = {"placements": "nope"}
        with self.assertRaisesRegex(ValueError, "list"):
            il.parse_placements(data)

    def test_missing_key(self):
        data = {}
        with self.assertRaisesRegex(ValueError, "placements"):
            il.parse_placements(data)


class ShouldSkipTests(unittest.TestCase):
    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(il.should_skip(Path(d) / "nonexistent.png"))

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "empty.png"
            p.write_text("", encoding="utf-8")
            self.assertFalse(il.should_skip(p))

    def test_non_empty_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "real.png"
            p.write_bytes(b"PNG")
            self.assertTrue(il.should_skip(p))


class MattePureTests(unittest.TestCase):
    def test_parse_bg_with_hash(self):
        self.assertEqual(il.parse_bg("#0A0E27"), (10, 14, 39))

    def test_parse_bg_without_hash(self):
        self.assertEqual(il.parse_bg("FFFFFF"), (255, 255, 255))

    def test_parse_bg_invalid(self):
        with self.assertRaises(ValueError):
            il.parse_bg("red")

    def test_border_mean_shift(self):
        self.assertEqual(il.border_mean_shift((12, 14, 39), (10, 14, 40)), (-2, 0, 1))

    def test_apply_shift_clamps(self):
        self.assertEqual(il.apply_shift((250, 5, 128), (10, -10, 0)), (255, 0, 128))

    def test_seam_deviation(self):
        self.assertEqual(il.seam_deviation((10, 15, 12), (10, 14, 39)), 27)

    def test_shift_then_deviation_zero(self):
        bg = (10, 14, 39)
        border = (12, 18, 30)
        shift = il.border_mean_shift(border, bg)
        moved = tuple(border[i] + shift[i] for i in range(3))
        self.assertEqual(il.seam_deviation(moved, bg), 0)


class GenDryRunTests(unittest.TestCase):
    def test_dry_run_jobs(self):
        with tempfile.TemporaryDirectory() as d:
            job = {
                "items": [
                    {"id": "a", "content": "cat"},
                    {"id": "b", "content": "dog"},
                ]
            }
            jp = Path(d) / "job.json"
            jp.write_text(json.dumps(job), encoding="utf-8")
            rp = Path(d) / "out.result.json"

            rc = il.run_gen(str(jp), str(Path(d) / "images"), str(rp), dry_run=True, jobs=4)
            self.assertEqual(rc, 0)

            res = json.loads(rp.read_text(encoding="utf-8"))
            self.assertTrue(res["dry_run"])
            self.assertEqual(len(res["items"]), 2)
            self.assertIn("total_cost", res)
            for it in res["items"]:
                self.assertTrue(it["ok"])


if __name__ == "__main__":
    unittest.main()
