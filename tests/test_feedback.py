# SPDX-License-Identifier: GPL-2.0
"""Отклик (haltia_paint.feedback), with paplay and feedbackd stood in for."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from haltia_paint.feedback import COLOUR_EVENT, PICTURE_EVENT, Feedback  # noqa: E402

SOUNDS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data",
                      "sounds")


class FeedbackTest(unittest.TestCase):
    def make(self, **kw):
        self.played, self.buzzed = [], []
        return Feedback(kw.pop("sounds", SOUNDS), "app.id", player=self.played.append,
                        bus=lambda app, event: self.buzzed.append((app, event)), **kw)

    def test_colour_and_picture(self):
        f = self.make()
        f.colour_done()
        f.picture_done()
        self.assertEqual([os.path.basename(a[1]) for a in self.played],
                         ["colour.oga", "picture.oga"])
        self.assertEqual(self.buzzed, [("app.id", COLOUR_EVENT), ("app.id", PICTURE_EVENT)])

    def test_a_miss_sounds_but_does_not_buzz(self):
        f = self.make()
        f.missed()
        self.assertEqual([os.path.basename(a[1]) for a in self.played], ["miss.oga"])
        self.assertEqual(self.buzzed, [])
        f = self.make(miss=False)
        f.missed()
        self.assertEqual(self.played, [])
        f = self.make(sound=False)
        f.missed()
        self.assertEqual(self.played, [])

    def test_each_can_be_off(self):
        f = self.make(sound=False)
        f.colour_done()
        self.assertEqual((self.played, len(self.buzzed)), ([], 1))
        f = self.make(vibration=False)
        f.colour_done()
        self.assertEqual((len(self.played), self.buzzed), (1, []))

    def test_no_sound_files_no_sound(self):
        with tempfile.TemporaryDirectory() as empty:
            f = self.make(sounds=empty)
            f.picture_done()
        self.assertEqual(self.played, [])

    def test_the_sounds_are_there(self):
        for name in ("colour.oga", "picture.oga", "miss.oga"):
            with open(os.path.join(SOUNDS, name), "rb") as fh:
                self.assertEqual(fh.read(4), b"OggS")


if __name__ == "__main__":
    unittest.main()
