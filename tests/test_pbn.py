# SPDX-License-Identifier: GPL-2.0
"""pbn.py on small made-up pictures (skipped without numpy and scipy)."""
import gzip
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import numpy as np
    from PIL import Image, ImageDraw
    import pbn
except ImportError:  # the check of a package without them
    pbn = None


def scene(lines=False):
    """A sky, a hill, a sun and a house, 400 x 300; with lines, each
    outlined in black as on a print."""
    img = Image.new("RGB", (400, 300), (150, 190, 235))
    pen = ImageDraw.Draw(img)
    width = 3 if lines else 0
    pen.rectangle((0, 180, 400, 300), fill=(90, 160, 70), outline=(20, 20, 20) if lines else None,
                  width=width)
    pen.ellipse((300, 30, 360, 90), fill=(250, 220, 60), outline=(20, 20, 20) if lines else None,
                width=width)
    pen.rectangle((80, 120, 180, 200), fill=(200, 80, 60), outline=(20, 20, 20) if lines else None,
                  width=width)
    pen.polygon(((70, 120), (130, 70), (190, 120)), fill=(120, 60, 40),
                outline=(20, 20, 20) if lines else None)
    # A broad black thing, which is not a line.
    pen.rectangle((240, 200, 300, 260), fill=(15, 15, 15))
    return img


@unittest.skipIf(pbn is None, "needs numpy, scipy and Pillow")
class PictureTest(unittest.TestCase):
    def test_regions_and_numbers(self):
        pic = pbn.picture(scene(), 40, 8, side=400, detail=3, raster=True)
        rgb, labels, colour_of, keep, ink, rows, cols, radius = pic["raster"]
        self.assertIsNone(ink)
        self.assertLessEqual(len(pic["regions"]), 40)
        self.assertGreaterEqual(len(pic["regions"]), 5)
        # Each number is in its own region, at its widest.
        for r in range(len(colour_of)):
            self.assertEqual(labels[rows[r], cols[r]], r)
        self.assertTrue((radius >= pbn.MIN_RADIUS).all())
        # Numbered light to dark, from 0.
        self.assertEqual(sorted({n for n, _l, _o in pic["regions"]}),
                         list(range(len(pic["palette"]))))

    def test_big_numbers_make_no_thin_regions(self):
        pic = pbn.picture(scene(), 40, 8, side=400, detail=3, min_radius=pbn.MIN_RADIUS_BIG,
                          raster=True)
        self.assertTrue((pic["raster"][7] >= pbn.MIN_RADIUS_BIG).all())

    def test_ink_keeps_lines_not_black_areas(self):
        lines = pbn.ink_lines(pbn.lightness(np.asarray(scene(lines=True))))
        self.assertTrue(lines[178:184, 20:60].any(axis=0).all())  # along the hill's edge
        self.assertFalse(lines[215:245, 255:285].any())  # inside the black square
        pic = pbn.picture(scene(lines=True), 40, 8, side=400, detail=3, ink=True)
        self.assertTrue(pic["ink"])
        svg = pbn.to_svg(pic)
        self.assertEqual(svg.count('data-ink="1"'), 1)
        # The outlines' black is not a colour to paint.
        self.assertNotIn("#%02x%02x%02x" % pbn.INK, pic["palette"])

    def test_more_ink_keeps_more(self):
        light = pbn.lightness(np.asarray(scene(lines=True)))
        few = pbn.ink_lines(light, ground=pbn.INK_GROUND[1])
        more = pbn.ink_lines(light, ground=pbn.INK_GROUND[2])
        self.assertGreaterEqual(more.sum(), few.sum())
        self.assertEqual(pbn.mode_name(True, 2), "big ink2")
        self.assertEqual(pbn.mode_name(False, 1), "ink")

    def test_merge_reaches_the_count(self):
        # Speckled noise: many small regions merged down to the count.
        rng = np.random.default_rng(3)
        idx = (rng.random((120, 160)) * 4).astype(np.int32)
        labels, colour_of = pbn.components(idx, 4)
        colours = pbn.lab(np.array([(200, 0, 0), (0, 200, 0), (0, 0, 200), (200, 200, 0)],
                                   np.uint8))
        labels, colour_of = pbn.merge(labels, colour_of, colours, np.zeros(idx.shape), 30,
                                      20, 1.0)
        self.assertLessEqual(len(colour_of), 30)
        self.assertEqual(labels.max() + 1, len(colour_of))
        # No two neighbours of one colour stay apart.
        a, b, _g = pbn.border_pairs(labels, np.zeros(idx.shape))
        self.assertFalse((colour_of[a] == colour_of[b]).any())

    def test_written_file(self):
        pic = pbn.picture(scene(), 40, 8, side=400, detail=3)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.svgz")
            pbn.write(pic, path, {"name": "Дом", "mode": "big"})
            with gzip.open(path) as fh:
                text = fh.read().decode()
        self.assertEqual(len(re.findall(r"<path [^>]*data-n=", text)), len(pic["regions"]))
        self.assertIn('data-count="%d"' % len(pic["regions"]), text)
        self.assertRegex(text, r'data-sig="[0-9a-f]{12}"')
        self.assertIn('data-name="Дом"', text)
        # The same picture made again has the same fingerprint.
        self.assertEqual(re.search(r'data-sig="(\w+)"', pbn.to_svg(pic)).group(1),
                         re.search(r'data-sig="(\w+)"', text).group(1))


if __name__ == "__main__":
    unittest.main()
