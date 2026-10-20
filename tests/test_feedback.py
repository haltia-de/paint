# SPDX-License-Identifier: GPL-2.0
"""Отклик (haltia_paint.feedback), with paplay and feedbackd stood in for."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from haltia_paint.feedback import COLOUR_EVENT, PICTURE_EVENT, TAP_EVENT, Feedback  # noqa: E402

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

    def test_taps_buzz_only_when_the_shell_leaves_them(self):
        with tempfile.TemporaryDirectory() as d:
            quiet = os.path.join(d, "quiet-taps")
            conf = os.path.join(d, "touchguard.conf")
            with open(conf, "w") as fh:
                fh.write("# taps\nbuzz_ms = 70\n")
            f = self.make(quiet_taps=quiet, touchguard=conf)
            f.tapped()
            self.assertEqual(self.buzzed, [])  # the shell buzzes them
            open(quiet, "w").close()
            f.tapped()
            self.assertEqual(self.buzzed, [("app.id", TAP_EVENT)])
            f.missed()
            self.assertEqual(len(self.buzzed), 1)  # a miss is not felt
            f.hit()
            self.assertEqual(len(self.buzzed), 2)
            for taps, felt in (("miss", [False, True]), ("both", [True, True]),
                               ("none", [False, False])):
                f.taps, self.buzzed[:] = taps, []
                f.hit()
                hit = bool(self.buzzed)
                f.missed()
                self.assertEqual([hit, len(self.buzzed) > hit], felt, taps)
            with open(conf, "w") as fh:
                fh.write("buzz_ms = 0\n")
            f = self.make(quiet_taps=quiet, touchguard=conf)
            f.tapped()
            self.assertEqual(self.buzzed, [])  # taps buzz nowhere then

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
