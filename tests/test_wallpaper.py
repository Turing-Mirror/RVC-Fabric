# -*- coding: utf-8 -*-
"""Wallpaper image pipeline (Pillow cover + blur + strength) — no Tk window."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.ui.wallpaper import (  # noqa: E402
    clamp_blur,
    clamp_opacity,
    clear_installed_wallpaper,
    cover_resize,
    install_wallpaper_file,
    process_wallpaper,
    resolve_wallpaper_path,
)


def _has_pil() -> bool:
    try:
        import PIL  # noqa: F401

        return True
    except ImportError:
        return False


class ClampTests(unittest.TestCase):
    def test_opacity(self):
        self.assertEqual(clamp_opacity(-5), 0)
        self.assertEqual(clamp_opacity(140), 100)
        self.assertEqual(clamp_opacity("42"), 42)

    def test_blur(self):
        self.assertEqual(clamp_blur(-1), 0)
        self.assertEqual(clamp_blur(99), 40)
        self.assertEqual(clamp_blur(8.6), 9)


@unittest.skipUnless(_has_pil(), "Pillow not installed")
class ProcessTests(unittest.TestCase):
    def _solid_png(self, path: Path, color=(30, 120, 200), size=(80, 60)) -> None:
        from PIL import Image

        Image.new("RGB", size, color).save(path)

    def test_cover_resize_and_process_size(self):
        from PIL import Image

        im = Image.new("RGB", (200, 100), (10, 20, 30))
        out = cover_resize(im, 100, 100)
        self.assertEqual(out.size, (100, 100))

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.png"
            self._solid_png(p, size=(120, 80))
            img = process_wallpaper(p, (160, 90), opacity=50, blur=5)
            self.assertEqual(img.size, (160, 90))
            self.assertEqual(img.mode, "RGB")

    def test_opacity_zero_is_fill(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "b.png"
            self._solid_png(p, color=(255, 0, 0))
            img = process_wallpaper(p, (40, 40), opacity=0, blur=0)
            # pure fill TM_BG-ish
            px = img.getpixel((0, 0))
            self.assertEqual(px, (247, 249, 251))

    def test_install_and_resolve(self):
        with tempfile.TemporaryDirectory() as td:
            ud = Path(td) / "User_Data"
            ud.mkdir()
            src = Path(td) / "src.jpg"
            self._solid_png(src)
            rel = install_wallpaper_file(src, ud)
            self.assertTrue(rel.startswith("wallpaper/"))
            got = resolve_wallpaper_path(rel, user_data=ud, root=Path(td))
            self.assertIsNotNone(got)
            self.assertTrue(got.is_file())
            clear_installed_wallpaper(ud)
            self.assertIsNone(
                resolve_wallpaper_path(rel, user_data=ud, root=Path(td))
            )


if __name__ == "__main__":
    unittest.main()
