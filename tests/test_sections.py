# SPDX-License-Identifier: GPL-2.0
"""Разделы галереи (haltia_paint.sections)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from haltia_paint import sections as s  # noqa: E402


def pic(pic_id, count, theme="Природа", name=None):
    return {"id": pic_id, "count": count, "theme": theme, "name": name or pic_id}


def claims(**props):
    return {prop: [{"mainsnak": {"datavalue": {"value": {"id": q}}}} for q in ids]
            for prop, ids in props.items()}


class SectionsTest(unittest.TestCase):
    def setUp(self):
        self.pics = [pic("builtin-fox", 280, "Животные"), pic("builtin-wave", 576, "Флот"),
                     pic("builtin-meadow", 120), pic("builtin-fuji", 290, "Японская гравюра"),
                     pic("photo-1", 300, ""), pic("wd-Q1-3b", 900, "Иван Шишкин")]
        self.states = {"builtin-fox": ("begun", 5), "builtin-fuji": ("begun", 9),
                       "builtin-meadow": ("done", 3)}

    def state(self, p):
        return self.states.get(p["id"], ("new", 0))

    def headings(self, order):
        return [(h, [p["id"] for p, _n in pics])
                for h, pics in s.sections(self.pics, order, self.state)]

    def test_by_theme(self):
        self.assertEqual(self.headings(s.BY_THEME), [
            ("Продолжить", ["builtin-fuji", "builtin-fox"]),  # the last painted first
            ("Мои фотографии", ["photo-1"]),
            ("Море и корабли", ["builtin-wave"]),  # Флот before 4.5
            ("Животные", ["builtin-fox"]),  # begun: still in its own section
            ("Японская гравюра", ["builtin-fuji"]),
            ("Разное", ["wd-Q1-3b"]),  # an artist where the theme was, before 4.5
            ("Готовые", ["builtin-meadow"]),  # finished: only there
        ])

    def test_by_difficulty(self):
        self.assertEqual(self.headings(s.BY_DIFFICULTY), [
            ("Продолжить", ["builtin-fuji", "builtin-fox"]),
            ("Средние", ["photo-1", "builtin-fox", "builtin-fuji"]),  # by theme within
            ("Сложные", ["builtin-wave"]),
            ("Очень сложные", ["wd-Q1-3b"]),
            ("Готовые", ["builtin-meadow"]),
        ])

    def test_notes_say_what_the_heading_does_not(self):
        by_theme = dict(s.sections(self.pics, s.BY_THEME, self.state))
        self.assertEqual(by_theme["Животные"][0][1], "280 областей")
        self.assertEqual(by_theme["Продолжить"][0][1], "Японская гравюра")
        by_level = dict(s.sections(self.pics, s.BY_DIFFICULTY, self.state))
        self.assertEqual(by_level["Сложные"][0][1], "Море и корабли")

    def test_easier_first_within_a_theme(self):
        pics = [pic("builtin-a", 500), pic("builtin-b", 120), pic("builtin-c", 300)]
        heading, cards = s.sections(pics, s.BY_THEME, lambda p: ("new", 0))[0]
        self.assertEqual([p["id"] for p, _n in cards], ["builtin-b", "builtin-c", "builtin-a"])

    def test_bands(self):
        self.assertEqual([s.difficulty(n) for n in (117, 150, 151, 350, 576, 651, 1000)],
                         ["Лёгкие", "Лёгкие", "Средние", "Средние", "Сложные",
                          "Очень сложные", "Очень сложные"])

    def test_plural(self):
        self.assertEqual([s.regions(n) for n in (1, 2, 5, 11, 12, 21, 302, 114, 1000)],
                         ["1 область", "2 области", "5 областей", "11 областей",
                          "12 областей", "21 область", "302 области", "114 областей",
                          "1000 областей"])

    def test_theme_from_wikidata(self):
        self.assertEqual(s.theme_of(claims(P136=["Q191163"])), "Природа")
        # A ukiyo-e landscape is a print.
        self.assertEqual(s.theme_of(claims(P136=["Q191163", "Q185905"])), "Японская гравюра")
        # No genre known: what it depicts; a woman with a cat goes to the animals.
        self.assertEqual(s.theme_of(claims(P136=["Q941875"], P180=["Q467", "Q146"])), "Животные")
        self.assertEqual(s.theme_of(claims(P180=["Q11446"])), "Море и корабли")
        self.assertEqual(s.theme_of({}), "Разное")

    def test_own_pictures_are_my_photos(self):
        self.assertEqual(s.theme(pic("wd-own-ab12", 300, "Мои фотографии")), "Мои фотографии")
        self.assertEqual(s.theme(pic("photo-ab12", 300, "")), "Мои фотографии")


if __name__ == "__main__":
    unittest.main()
