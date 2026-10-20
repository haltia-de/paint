# SPDX-License-Identifier: GPL-2.0-or-later
"""Подсветка (haltia_paint.highlight), drawn into small surfaces (skipped
without pycairo)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import cairo
    from haltia_paint.highlight import CELL, COLOURS, DEFAULT, STYLES, Highlight
except ImportError:
    cairo = None


def draw(source, size=48):
    """The surface's pixels as (r, g, b) bytes, filled with source."""
    img = cairo.ImageSurface(cairo.FORMAT_RGB24, size, size)
    cr = cairo.Context(img)
    cr.set_source(source)
    cr.paint()
    img.flush()
    data = bytes(img.get_data())
    stride = img.get_stride()
    return [[(data[y * stride + 4 * x + 2], data[y * stride + 4 * x + 1], data[y * stride + 4 * x])
             for x in range(size)] for y in range(size)]


@unittest.skipIf(cairo is None, "needs pycairo")
class HighlightTest(unittest.TestCase):
    def test_unknown_choices_fall_back(self):
        look = Highlight("sparkles", None)
        self.assertEqual((look.style, look.colour), DEFAULT)

    def test_every_choice_draws(self):
        for style, _name in STYLES:
            for colour, _name in COLOURS:
                px = draw(Highlight(style, colour).mark((0.6, 0.65, 0.55)).source(1.0))
                kinds = {p for row in px for p in row}
                if style == "fill":
                    self.assertEqual(len(kinds), 1)
                else:
                    # A pattern: two colours at least, far apart in lightness.
                    light = sorted(sum(p) for p in kinds)
                    self.assertGreater(light[-1] - light[0], 200, (style, colour))

    def test_pattern_keeps_its_size_on_screen(self):
        # At scale 3 the pattern repeats every CELL pixels still.
        px = draw(Highlight("checker", "grey").mark((0, 0, 0)).source(3.0), 4 * CELL)
        self.assertEqual(px[1][1], px[1][1 + CELL])
        self.assertNotEqual(px[1][1], px[1][1 + CELL // 2])

    def test_every_colour_has_an_ink(self):
        from haltia_paint.highlight import INKS
        self.assertEqual({c for c, _n in COLOURS} - {"number"}, set(INKS))

    def test_light_colour_on_dark_ground(self):
        # Yellow stripes would vanish on white: they get a dark ground.
        px = draw(Highlight("hatch", "yellow").mark((0, 0, 0)).source(1.0))
        self.assertLess(min(sum(p) for row in px for p in row), 200)

    def test_inverted_swaps_colour_and_ground(self):
        # Grey stripes on light: mostly light; inverted, mostly grey.
        def mean(look):
            px = draw(look.mark((0, 0, 0)).source(1.0))
            return sum(sum(p) for row in px for p in row) / (len(px) * len(px[0]))
        self.assertGreater(mean(Highlight("hatch", "grey")),
                           mean(Highlight("hatch", "grey", inverted=True)) + 100)
        # A fill: the colour itself, darker than the tint.
        self.assertGreater(mean(Highlight("fill", "blue")),
                           mean(Highlight("fill", "blue", inverted=True)))

    def test_number_colour_follows_the_number(self):
        a = Highlight("fill", "number").mark((0.9, 0.1, 0.1))
        b = Highlight("fill", "number").mark((0.1, 0.1, 0.9))
        self.assertNotEqual(draw(a.source(1.0))[0][0], draw(b.source(1.0))[0][0])


if __name__ == "__main__":
    unittest.main()
