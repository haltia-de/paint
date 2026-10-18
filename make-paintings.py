#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Turn public-domain paintings into the built-in b8k-paint pictures.

  make-paintings.py CACHE_DIR [SLUG...]

downloads each painting from Wikimedia Commons (1200 px wide), or each
drawing from OpenClipart, into CACHE_DIR, then writes
pictures/<slug>.svgz with pbn.py: level 2 of about 120 regions, 3 of
about 300, 4 of about 600 (see LEVELS there). The paintings and prints
are by artists who died more than 70 years ago, so they are in the
public domain; OpenClipart drawings are CC0. PAINTINGS names each source.
Needs numpy and scipy, and cairosvg for the drawings.
"""
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

import pbn

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pictures")
# Wikimedia asks for a User-Agent that says who is asking.
AGENT = "b8k-paint/1.0 (https://github.com/trudenboy/lenovo-b8000h-linux)"

# slug, source, name, theme, level, and optionally the part to use (x0,
# y0, x1, y1 as fractions: no text, no book margins). The source is a
# Commons file, or "openclipart:ID" for an OpenClipart drawing (CC0).
PAINTINGS = [
    ("golden-autumn", "Levitan Zolotaya Osen.jpg", "Золотая осень", "Природа", 4),
    ("rye", "Ivan Shishkin - Рожь - Google Art Project.jpg", "Рожь", "Природа", 4),
    ("winter", "Ivan Shishkin - Winter.JPG", "Зима", "Северная природа", 4),
    ("rainbow-sea", "Aivazovsky, Rainbow.JPG", "Радуга над морем", "Флот", 4),
    ("brig-mercury", "Aivazovsky, Brig Mercury Attacked by Two Turkish Ships 1892.jpg",
     "Бриг «Меркурий»", "Военный флот", 4),
    ("red-fuji", "Katsushika Hokusai - Fine Wind, Clear Morning (Gaifū kaisei) - Google Art Project.jpg",
     "Красная Фудзи", "Природа", 3),
    ("sunflowers", "Vincent van Gogh - Sunflowers (1888, National Gallery London).jpg",
     "Подсолнухи", "Природа", 3),
    ("almond", "Vincent van Gogh - Almond blossom - Google Art Project.jpg",
     "Цветущий миндаль", "Природа", 3),
    ("plum-garden", "Ando Hiroshige - Plum Garden, Kameido - Google Art Project.jpg",
     "Сливовый сад", "Природа", 3),
    ("egrets-snow", "Ohara Shoson (Koson), Egrets in Snow, 1927.jpg", "Цапли в снегу",
     "Северная природа", 3),
    ("eagle-snow", "Fukagawa Susaki and Jumantsubo (5759415218).jpg", "Орёл над снежной равниной",
     "Северная природа", 3),
    ("fishing-boats", "Vincent van Gogh - Vissersboten op het strand van Les Saintes-Maries-de-la-Mer - Google Art Project.jpg",
     "Лодки на берегу", "Флот", 3),
    ("dazzle-ships", "Dazzle-ships in Drydock at Liverpool.jpg", "Корабли в доке",
     "Военный флот", 3),
    ("kingfisher", "Koson - kingfisher.jpg", "Зимородок", "Животные", 3),
    ("carp", "Koson - leaping-carp.jpg", "Карп", "Животные", 3),
    ("parrot", "Koson-Hoson Papageie.jpg", "Попугай", "Животные", 3),
    ("fox", "Koson - fox-in-the-reeds.jpg", "Лиса в камышах", "Животные", 3),
    ("hare", "Albrecht Dürer - Hare, 1502 - Google Art Project.jpg", "Заяц", "Животные", 3),
    ("north", "Arkhip Kuindzhi - North.jpg", "Север", "Северная природа", 4),
    ("swans", "Rylov Blue Expanse.jpg", "В голубом просторе", "Северная природа", 4),
    ("great-wave", "The Great Wave off Kanagawa.jpg", "Большая волна", "Флот", 4),
    ("ninth-wave", "Aivazovsky, Ivan - The Ninth Wave.jpg", "Девятый вал", "Флот", 5),
    ("sevastopol", "Ivan Constantinovich Aivazovsky - The Russian Squadron on the Sebastopol Roads.jpg",
     "Эскадра на Севастопольском рейде", "Военный флот", 4),
    ("feodosia", "Aivazovsky - Black Sea Fleet in the Bay of Theodosia.jpg",
     "Черноморский флот", "Военный флот", 4),
    ("twelve-apostles", 'Aivasovsky I C Ship "Twelve Apostles".jpg',
     "Корабль «Двенадцать апостолов»", "Военный флот", 4),
    ("crow", "Cawing crow by Ohara Koson.jpg", "Ворона", "Животные", 3),
    ("pine-morning", "Shishkin, Ivan - Morning in a Pine Forest.jpg",
     "Утро в сосновом лесу", "Животные", 5),
    ("monarch", "Monarch of the Glen, Edwin Landseer, 1851.jpg", "Король долины",
     "Животные", 5),
    ("ship-grove", "Корабельная роща (Шишкин).jpg", "Корабельная роща", "Природа", 5),
    ("birch-grove", "Kuindzhi Birch Grove 1879.jpg", "Берёзовая роща", "Природа", 5),
    ("rooks", "Aleksey Savrasov - Грачи прилетели - Google Art Project.jpg",
     "Грачи прилетели", "Природа", 5),
    ("march", "Isaak Levitan - March.jpg", "Март", "Северная природа", 5),
    ("eternal-peace", "LevitanAboveEternalPeace.jpg", "Над вечным покоем",
     "Северная природа", 5),
    ("among-waves", "Ivan Konstantinovich Aivazovsky - Among the Waves, 1898.jpg",
     "Среди волн", "Флот", 5),
    ("sinop", "Battle of Sinop.jpg", "Синопский бой", "Военный флот", 5),
    ("ploughing", "Rosa Bonheur - Ploughing in Nevers - Google Art Project.jpg",
     "Пахота в Ниверне", "Животные", 5),
    ("horse-fair", "Rosa Bonheur, The Horse Fair, 1852–55.jpg", "Конская ярмарка",
     "Животные", 5),
]
# The level of a painting above, as made now: the 128-cell paintings of
# the grid days are 600-region ones too.
LEVEL = {2: 2, 3: 3, 4: 4, 5: 4}


def fetch(cache, name):
    path = os.path.join(cache, name.replace("/", "_").replace(":", "-"))
    if name.startswith("openclipart:"):
        # A drawing: its SVG, drawn on white at the size the pictures use.
        if not os.path.exists(path + ".png"):
            import cairosvg
            req = urllib.request.Request("https://openclipart.org/download/" + name[12:],
                                         headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                svg = r.read()
            cairosvg.svg2png(bytestring=svg, write_to=path + ".png",
                             output_width=pbn.SIDE, background_color="white")
        return path + ".png"
    if not os.path.exists(path):
        url = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
               + urllib.parse.quote(name) + "?width=1200")
        req = urllib.request.Request(url, headers={"User-Agent": AGENT})
        for wait in (20, 40, 80, 160, 0):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                break
            except urllib.error.HTTPError as exc:
                # Commons asks to slow down now and then.
                if exc.code != 429 or not wait:
                    raise
                time.sleep(wait)
        with open(path, "wb") as fh:
            fh.write(data)
        time.sleep(2)
    return path


def main():
    cache = sys.argv[1]
    only = set(sys.argv[2:])
    os.makedirs(cache, exist_ok=True)
    for slug, name, title, theme, level, *crop in PAINTINGS:
        if only and slug not in only:
            continue
        level = LEVEL[level]
        regions, colours, detail = pbn.LEVELS[level]
        pic = pbn.picture(Image.open(fetch(cache, name)), regions, colours, detail=detail,
                          crop=crop[0] if crop else None)
        pbn.write(pic, os.path.join(OUT, slug + ".svgz"),
                  {"name": title, "theme": theme, "level": level, "source": name})
        print(slug, len(pic["regions"]), len(pic["palette"]))


if __name__ == "__main__":
    main()
