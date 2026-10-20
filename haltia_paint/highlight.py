# SPDX-License-Identifier: GPL-2.0-or-later
"""Подсветка: how the regions of the chosen number stand out on the board.

A plain colour got lost next to painted regions of a like colour (a light
blue next to a painted sky). Painted regions are always flat, so a
pattern (stripes, a checker) is told apart from any of them; the setting
picks the pattern and its colour, Настройки → Подсветка, and whether its
colours are the other way round (inverted: the colour as the ground and
light or dark lines on it; a fill in the colour itself, not a tint).

    look = Highlight("hatch", "grey", inverted=False)
    mark = look.mark(number_rgb)     # what fill(i) gives draw_regions
    cr.set_source(mark.source(scale))  # in user space scaled by scale
    look.number                       # (text colour, halo colour)

The pattern keeps CELL pixels on the screen at every zoom, and lines up
across tiles (its origin is the board's).
"""
import cairo

STYLES = (("hatch", "Штриховка"), ("checker", "Шахматка"), ("fill", "Заливка"))
COLOURS = (("grey", "Серый"), ("blue", "Голубой"), ("yellow", "Жёлтый"),
           ("number", "Цвет номера"),
           # Bright ones a painting hardly has, so they stand out on any.
           ("magenta", "Малиновый"), ("violet", "Фиолетовый"), ("turquoise", "Бирюзовый"),
           ("lime", "Салатовый"), ("orange", "Оранжевый"))
DEFAULT = ("hatch", "grey")
# The colours to choose, as the stripes or squares are drawn.
INKS = {"grey": (0.40, 0.40, 0.43), "blue": (0.20, 0.47, 0.90), "yellow": (0.93, 0.72, 0.05),
        "magenta": (0.86, 0.08, 0.55), "violet": (0.50, 0.22, 0.90),
        "turquoise": (0.00, 0.70, 0.72), "lime": (0.50, 0.82, 0.00),
        "orange": (1.00, 0.45, 0.00)}
# Pixels on the screen of one repeat of the pattern.
CELL = 12
LIGHT, DARK = (0.97, 0.97, 0.96), (0.16, 0.16, 0.18)


def luminance(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def mix(a, b, share):
    """a moved share of the way to b."""
    return tuple(x + (y - x) * share for x, y in zip(a, b))


class Mark:
    """The look of one number's regions, as a cairo source per scale."""

    def __init__(self, style, ink, inverted=False):
        self.style = style
        self.ink = ink
        self.inverted = inverted
        self._sources = {}

    def source(self, scale):
        key = round(scale, 5)
        if key not in self._sources:
            self._sources[key] = self._make(scale)
        return self._sources[key]

    def _make(self, scale):
        if self.style == "fill":
            # A light tint of the colour, light enough for a dark number;
            # inverted, the colour itself (the number has its white halo).
            return cairo.SolidPattern(*(self.ink if self.inverted
                                        else mix(self.ink, (1, 1, 1), 0.45)))
        # Light ground under dark stripes, dark ground under light ones,
        # so they show whatever the colour; inverted, the other way round.
        ground, ink = (LIGHT if luminance(self.ink) < 0.6 else DARK), self.ink
        if self.inverted:
            ground, ink = ink, ground
        tile = cairo.ImageSurface(cairo.FORMAT_RGB24, CELL, CELL)
        cr = cairo.Context(tile)
        cr.set_source_rgb(*ground)
        cr.paint()
        cr.set_source_rgb(*ink)
        if self.style == "checker":
            half = CELL / 2
            cr.rectangle(0, 0, half, half)
            cr.rectangle(half, half, half, half)
            cr.fill()
        else:
            # Thin lines close together (two to a cell): dense enough to
            # see in a small region, still mostly ground between them.
            cr.set_line_width(CELL * 0.12)
            for d in (-CELL, -CELL / 2, 0, CELL / 2, CELL):
                cr.move_to(d, CELL)
                cr.line_to(d + CELL, 0)
            cr.stroke()
        tile.flush()
        pattern = cairo.SurfacePattern(tile)
        pattern.set_extend(cairo.EXTEND_REPEAT)
        # User space (picture units) times scale is the board's pixels.
        pattern.set_matrix(cairo.Matrix(xx=scale, yy=scale))
        return pattern


class Highlight:
    """A style (STYLES) and a colour (COLOURS), its colours inverted or
    not; unknown ones fall back to DEFAULT."""

    def __init__(self, style=DEFAULT[0], colour=DEFAULT[1], inverted=False):
        self.style = style if style in dict(STYLES) else DEFAULT[0]
        self.colour = colour if colour in dict(COLOURS) else DEFAULT[1]
        self.inverted = bool(inverted)
        self._marks = {}

    def mark(self, number_rgb):
        """The Mark for the regions of a number of this colour."""
        ink = tuple(number_rgb) if self.colour == "number" else INKS[self.colour]
        if ink not in self._marks:
            self._marks[ink] = Mark(self.style, ink, self.inverted)
        return self._marks[ink]

    @property
    def number(self):
        """How the chosen number's numbers are written: (colour, halo)."""
        return (0.08, 0.09, 0.11), (1.0, 1.0, 1.0)
