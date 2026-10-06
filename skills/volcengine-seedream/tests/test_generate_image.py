"""Unit tests for generate_image.py.

These tests do not call the Ark API and do not spend money.
Run with: python -m unittest
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add the scripts directory to the import path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import generate_image as gi


class NormalizeModelNameTests(unittest.TestCase):
    def test_short_aliases(self):
        self.assertEqual(gi.normalize_model_name("flash"), "5.0-flash")
        self.assertEqual(gi.normalize_model_name("pro"), "5.0-pro")
        self.assertEqual(gi.normalize_model_name("lite"), "5.0-lite")

    def test_friendly_aliases(self):
        self.assertEqual(gi.normalize_model_name("5.0-flash"), "5.0-flash")
        self.assertEqual(gi.normalize_model_name("5.0-pro"), "5.0-pro")
        self.assertEqual(gi.normalize_model_name("5.0-lite"), "5.0-lite")
        self.assertEqual(gi.normalize_model_name("4.0"), "4.0")
        self.assertEqual(gi.normalize_model_name("4.5"), "4.5")
        self.assertEqual(gi.normalize_model_name("5.0"), "5.0")

    def test_raw_ids(self):
        self.assertEqual(
            gi.normalize_model_name("doubao-seedream-5-0-flash-260915"),
            "5.0-flash",
        )
        self.assertEqual(
            gi.normalize_model_name("doubao-seedream-5-0-pro-260628"),
            "5.0-pro",
        )
        self.assertEqual(
            gi.normalize_model_name("doubao-seedream-4-0-20260415"),
            "4.0",
        )
        self.assertEqual(
            gi.normalize_model_name("doubao-seedream-4-5-251128"),
            "4.5",
        )

    def test_endpoint_id_not_misclassified_as_4_0(self):
        # The old loose "4-0" substring match wrongly classified this as 4.0.
        self.assertIsNone(gi.normalize_model_name("ep-2024-04-15"))

    def test_unknown(self):
        self.assertIsNone(gi.normalize_model_name("foo"))
        self.assertIsNone(gi.normalize_model_name(""))


class ResolveSizeTests(unittest.TestCase):
    def test_named_sizes_without_aspect(self):
        self.assertEqual(gi.resolve_size("1K", None), (1024, 1024))
        self.assertEqual(gi.resolve_size("1.5K", None), (1536, 1536))
        self.assertEqual(gi.resolve_size("2K", None), (2048, 2048))
        self.assertEqual(gi.resolve_size("4K", None), (4096, 4096))

    def test_wxh(self):
        self.assertEqual(gi.resolve_size("1024x768", None), (1024, 768))
        self.assertEqual(gi.resolve_size("800X600", None), (800, 600))

    def test_4k_with_aspect_rejected(self):
        with self.assertRaisesRegex(ValueError, "4K.*不支持 aspect"):
            gi.resolve_size("4K", "16:9")

    def test_aspect_1_5k(self):
        self.assertEqual(gi.resolve_size("1.5K", "16:9"), (2048, 1152))

    def test_aspect_2k(self):
        self.assertEqual(gi.resolve_size("2K", "16:9"), (2048, 1152))

    def test_unknown_aspect(self):
        with self.assertRaisesRegex(ValueError, "未知 aspect"):
            gi.resolve_size("1.5K", "5:4")

    def test_invalid_size_format(self):
        # Malformed WxH -> "格式错误".
        with self.assertRaisesRegex(ValueError, "格式错误"):
            gi.resolve_size("1024x768x3", None)
        # Unknown named size -> "不支持".
        with self.assertRaisesRegex(ValueError, "不支持"):
            gi.resolve_size("3K", None)
        with self.assertRaisesRegex(ValueError, "不支持"):
            gi.resolve_size("abc", None)


class GetSizeTierTests(unittest.TestCase):
    def test_1_5k_tier_by_total_pixels(self):
        # 2048x1152 is 2.36M pixels -> still 1.5K tier.
        self.assertEqual(gi.get_size_tier(2048, 1152), "1.5K")
        self.assertEqual(gi.get_size_tier(1536, 1536), "1.5K")
        self.assertEqual(gi.get_size_tier(1024, 1024), "1.5K")

    def test_2k_tier(self):
        self.assertEqual(gi.get_size_tier(2048, 2048), "2K")
        self.assertEqual(gi.get_size_tier(2560, 1440), "2K")  # 3.69M pixels
        # 1920x1080 is only 2.07M -> stays in the 1.5K tier.
        self.assertEqual(gi.get_size_tier(1920, 1080), "1.5K")

    def test_4k_tier(self):
        self.assertEqual(gi.get_size_tier(4096, 4096), "4K")

    def test_too_large(self):
        self.assertIsNone(gi.get_size_tier(5000, 5000))


class EstimateCostLineTests(unittest.TestCase):
    def test_simple(self):
        line = gi.estimate_cost_line("5.0-flash", "1.5K", 1, False)
        self.assertIn("¥0.12", line)

    def test_multiple(self):
        line = gi.estimate_cost_line("5.0-pro", "2K", 2, False)
        self.assertIn("¥1.20", line)

    def test_sequential_range(self):
        line = gi.estimate_cost_line("5.0-pro", "1.5K", 2, False, max_images=3, sequential=True)
        self.assertIn("¥0.60", line)
        self.assertIn("¥1.80", line)
        self.assertIn("最多产出 3 张", line)

    def test_sequential_ignored_when_false(self):
        # max_images > 1 but sequential=False -> single value, not range.
        line = gi.estimate_cost_line("5.0-pro", "1.5K", 2, False, max_images=3, sequential=False)
        self.assertIn("¥0.60", line)
        self.assertNotIn("~", line)

    def test_unknown_model(self):
        line = gi.estimate_cost_line(None, "1.5K", 1, False)
        self.assertIn("未知", line)

    def test_4_0_unknown_price(self):
        line = gi.estimate_cost_line("4.0", "4K", 1, False)
        self.assertIn("未知", line)

    def test_flash_2k_unverified(self):
        line = gi.estimate_cost_line("5.0-flash", "2K", 1, False)
        self.assertIn("未证", line)

    def test_reference_surcharge(self):
        line = gi.estimate_cost_line("5.0-pro", "1.5K", 1, True)
        self.assertIn("输入图", line)


class ExtForTests(unittest.TestCase):
    def test_png(self):
        self.assertEqual(gi._ext_for(b"\x89PNG\r\n\x1a\n" + b"data"), ".png")

    def test_jpg(self):
        self.assertEqual(gi._ext_for(b"\xff\xd8\xff" + b"data"), ".jpg")

    def test_webp(self):
        self.assertEqual(gi._ext_for(b"RIFF" + b"xxxx" + b"WEBP" + b"data"), ".webp")

    def test_gif(self):
        self.assertEqual(gi._ext_for(b"GIF87a" + b"data"), ".gif")
        self.assertEqual(gi._ext_for(b"GIF89a" + b"data"), ".gif")

    def test_unknown_defaults_to_png(self):
        self.assertEqual(gi._ext_for(b"unknown"), ".png")


class SanitizeFilenameTests(unittest.TestCase):
    def test_basename_and_illegal_chars(self):
        self.assertEqual(gi.sanitize_filename("../../x"), "x")
        self.assertEqual(gi.sanitize_filename('a<b>:"c|?*d'), "abcd")

    def test_empty_becomes_default(self):
        self.assertEqual(gi.sanitize_filename(""), "seedream")
        self.assertEqual(gi.sanitize_filename("<>"), "seedream")


class UniquePathTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(__file__).resolve().parent / "_unique_path_tmp"
        self.tmpdir.mkdir(exist_ok=True)
        # Clean leftovers.
        for p in self.tmpdir.iterdir():
            p.unlink()

    def tearDown(self):
        for p in self.tmpdir.iterdir():
            p.unlink()
        self.tmpdir.rmdir()

    def test_no_conflict(self):
        p = gi.unique_path(self.tmpdir, "seedream", ".png")
        self.assertEqual(p, self.tmpdir / "seedream.png")

    def test_adds_numeric_suffix(self):
        (self.tmpdir / "seedream.png").write_text("x")
        p = gi.unique_path(self.tmpdir, "seedream", ".png")
        self.assertEqual(p, self.tmpdir / "seedream_1.png")
        p.write_text("y")
        p2 = gi.unique_path(self.tmpdir, "seedream", ".png")
        self.assertEqual(p2, self.tmpdir / "seedream_2.png")


if __name__ == "__main__":
    unittest.main()
