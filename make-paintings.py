#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Turn public-domain paintings into the built-in haltia-paint pictures.

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
AGENT = "haltia-paint/4.3 (https://github.com/haltia-de/paint)"

# slug, source, name, theme, level, and optionally the part to use (x0,
# y0, x1, y1 as fractions: no text, no book margins). The source is a
# Commons file, or "openclipart:ID" for an OpenClipart drawing (CC0).
PAINTINGS = [
    ("golden-autumn", "Levitan Zolotaya Osen.jpg", "Золотая осень", "Природа", 4),
    ("rye", "Ivan Shishkin - Рожь - Google Art Project.jpg", "Рожь", "Природа", 4),
    ("winter", "Ivan Shishkin - Winter.JPG", "Зима", "Природа", 4),
    ("rainbow-sea", "Aivazovsky, Rainbow.JPG", "Радуга над морем", "Море и корабли", 4),
    ("brig-mercury", "Aivazovsky, Brig Mercury Attacked by Two Turkish Ships 1892.jpg",
     "Бриг «Меркурий»", "Море и корабли", 4),
    ("red-fuji", "Katsushika Hokusai - Fine Wind, Clear Morning (Gaifū kaisei) - Google Art Project.jpg",
     "Красная Фудзи", "Природа", 3),
    ("sunflowers", "Vincent van Gogh - Sunflowers (1888, National Gallery London).jpg",
     "Подсолнухи", "Природа", 3),
    ("almond", "Vincent van Gogh - Almond blossom - Google Art Project.jpg",
     "Цветущий миндаль", "Природа", 3),
    ("plum-garden", "Ando Hiroshige - Plum Garden, Kameido - Google Art Project.jpg",
     "Сливовый сад", "Природа", 3),
    ("egrets-snow", "Ohara Shoson (Koson), Egrets in Snow, 1927.jpg", "Цапли в снегу",
     "Природа", 3),
    ("eagle-snow", "Fukagawa Susaki and Jumantsubo (5759415218).jpg", "Орёл над снежной равниной",
     "Природа", 3),
    ("fishing-boats", "Vincent van Gogh - Vissersboten op het strand van Les Saintes-Maries-de-la-Mer - Google Art Project.jpg",
     "Лодки на берегу", "Море и корабли", 3),
    ("dazzle-ships", "Dazzle-ships in Drydock at Liverpool.jpg", "Корабли в доке",
     "Море и корабли", 3),
    ("kingfisher", "Koson - kingfisher.jpg", "Зимородок", "Животные", 3),
    ("carp", "Koson - leaping-carp.jpg", "Карп", "Животные", 3),
    ("parrot", "Koson-Hoson Papageie.jpg", "Попугай", "Животные", 3),
    ("fox", "Koson - fox-in-the-reeds.jpg", "Лиса в камышах", "Животные", 3),
    ("hare", "Albrecht Dürer - Hare, 1502 - Google Art Project.jpg", "Заяц", "Животные", 3),
    ("north", "Arkhip Kuindzhi - North.jpg", "Север", "Природа", 4),
    ("swans", "Rylov Blue Expanse.jpg", "В голубом просторе", "Природа", 4),
    ("great-wave", "The Great Wave off Kanagawa.jpg", "Большая волна", "Море и корабли", 4),
    ("ninth-wave", "Aivazovsky, Ivan - The Ninth Wave.jpg", "Девятый вал", "Море и корабли", 5),
    ("sevastopol", "Ivan Constantinovich Aivazovsky - The Russian Squadron on the Sebastopol Roads.jpg",
     "Эскадра на Севастопольском рейде", "Море и корабли", 4),
    ("feodosia", "Aivazovsky - Black Sea Fleet in the Bay of Theodosia.jpg",
     "Черноморский флот", "Море и корабли", 4),
    ("twelve-apostles", 'Aivasovsky I C Ship "Twelve Apostles".jpg',
     "Корабль «Двенадцать апостолов»", "Море и корабли", 4),
    ("crow", "Cawing crow by Ohara Koson.jpg", "Ворона", "Животные", 3),
    ("pine-morning", "Shishkin, Ivan - Morning in a Pine Forest.jpg",
     "Утро в сосновом лесу", "Животные", 5),
    ("monarch", "Monarch of the Glen, Edwin Landseer, 1851.jpg", "Король долины",
     "Животные", 5),
    ("ship-grove", "Корабельная роща (Шишкин).jpg", "Корабельная роща", "Природа", 5),
    ("birch-grove", "Kuindzhi Birch Grove 1879.jpg", "Берёзовая роща", "Природа", 5),
    ("rooks", "Aleksey Savrasov - Грачи прилетели - Google Art Project.jpg",
     "Грачи прилетели", "Природа", 5),
    ("march", "Isaak Levitan - March.jpg", "Март", "Природа", 5),
    ("eternal-peace", "LevitanAboveEternalPeace.jpg", "Над вечным покоем",
     "Природа", 5),
    ("among-waves", "Ivan Konstantinovich Aivazovsky - Among the Waves, 1898.jpg",
     "Среди волн", "Море и корабли", 5),
    ("sinop", "Battle of Sinop.jpg", "Синопский бой", "Море и корабли", 5),
    ("ploughing", "Rosa Bonheur - Ploughing in Nevers - Google Art Project.jpg",
     "Пахота в Ниверне", "Животные", 5),
    ("horse-fair", "Rosa Bonheur, The Horse Fair, 1852–55.jpg", "Конская ярмарка",
     "Животные", 5),
    # Japanese prints, a section of their own.
    ("koson-tit", "Vintage Christmas illustration digitally enhanced by rawpixel-com-18.jpg",
     "Синица на цветущей вишне", "Японская гравюра", 3),
    ("koson-crow-blossom", "Crow and blossom by Ohara Koson cropped.jpg", "Ворона и цветы",
     "Японская гравюра", 3),
    ("koson-pheasant", "Fazant op kersenbloesemtak, AK-RAK-2000-13.jpg", "Фазан на ветке вишни",
     "Японская гравюра", 3),
    ("koson-lilies", "Lelies Teppoyuri, RP-T-1999-228.jpg", "Лилии", "Японская гравюра", 3),
    ("koson-snow-bridge", "Two women in snow on Yanagi Bridge (5759536190) (cropped).jpg",
     "Снег на мосту Янаги", "Японская гравюра", 3),
    ("koson-cat-goldfish",
     "Ohara koson, gatto e vasca con pesci rossi, 1933, xilografia colorata.jpg",
     "Кошка и золотые рыбки", "Японская гравюра", 3),
    ("koson-owl-moon", "Scops Owl, Cherry Blossoms, and Moon by Shōson.jpg",
     "Сова, вишня и луна", "Японская гравюра", 3),
    ("koson-waterside", "Bloemen aan waterkant, AK-RAK-2000-7.jpg", "Цветы у воды",
     "Японская гравюра", 3),
    ("koson-birds-bamboo", "Ohara Koson 001.jpg", "Птицы и бамбук", "Японская гравюра", 3),
    ("fuji-gotenyama", "Katsushika Hokusai, Goten-yama hill, Shinagawa on the Tōkaidō, ca. 1832.jpg",
     "Холм Готэн-яма в Синагаве", "Японская гравюра", 3),
    ("fuji-mishima", "Mishima Pass in Kai Province LCCN2008661008.jpg", "Перевал Мисима",
     "Японская гравюра", 3),
    ("fuji-noboto", "Bay of Noboto.jpg", "Залив Нобото", "Японская гравюра", 3),
    ("fuji-tago", "Shore of Tago Bay, Ejiri at Tokaido.jpg", "Берег залива Таго",
     "Японская гравюра", 3),
    ("fuji-mannen", "Fukagawa mannenbashi shita LCCN2008660637.jpg", "Под мостом Маннэн",
     "Японская гравюра", 3),
    ("fuji-isawa", "Dawn at Isawa in Kai Province LCCN2008661002.jpg", "Рассвет в Исаве",
     "Японская гравюра", 3),
    ("fuji-sazai", "Sazai Hall, Temple of Five Hundred Rankan LCCN2008661004.jpg",
     "Павильон Садзаи", "Японская гравюра", 3),
    ("fuji-suwa", "Lake Suwa in the Shinano province.jpg", "Озеро Сува", "Японская гравюра", 3),
    ("fuji-ono-shinden", "Hokusai31 ono-shinden.jpg", "Оно-Синдэн", "Японская гравюра", 3),
    ("fuji-senju", "Senju in the Musachi provimce.jpg", "Сэндзю", "Японская гравюра", 3),
    ("fuji-katakura", "The Tea plantation of Katakura in the Suruga province.jpg",
     "Чайная плантация Катакура", "Японская гравюра", 3),
    ("fuji-enoshima", "Enoshima in Sagami Province LCCN2008661007.jpg", "Остров Эносима",
     "Японская гравюра", 3),
    ("fuji-shichiri",
     "Seven-mile beach in Sagami province (Sōshū Shichiri-ga-hama) (CBL J 2745).jpg",
     "Берег Ситири-га-хама", "Японская гравюра", 3),
    ("fuji-kawaguchi", "Hokusai42 fuji-lake.jpg", "Фудзи в озере Кавагути", "Японская гравюра", 3),
    ("fuji-totomi", "The Fuji from the mountains of Totomi.jpg", "Фудзи с гор Тотоми",
     "Японская гравюра", 3),
    ("edo-koume", "NDL-DC 1303310-Utagawa Hiroshige-名所江戸百景 小梅堤-crd.jpg",
     "Насыпь Коумэ", "Японская гравюра", 3),
    ("edo-hachiman-garden", "NDL-DC 1303263-Utagawa Hiroshige-名所江戸百景 深川八まん山ひらき-crd.jpg",
     "Сад у храма Хатимана", "Японская гравюра", 3),
    ("edo-takinogawa", "NDL-DC 1303294-Utagawa Hiroshige-名所江戸百景 王子滝の川-crd.jpg",
     "Река Такиногава", "Японская гравюра", 3),
    ("edo-suijin", "NDL-DC 1303239-Utagawa Hiroshige-名所江戸百景 隅田川水神の森真崎-crd.jpg",
     "Роща Суйдзин на реке Сумида", "Японская гравюра", 3),
    ("edo-ekoin", "NDL-DC 1303209-Utagawa Hiroshige-名所江戸百景 両ごく回向院元柳橋-crd.jpg",
     "Храм Экоин и мост Мото-Янаги", "Японская гравюра", 3),
    ("edo-great-waterfall",
     "NDL-DC 1303223-Utagawa Hiroshige-名所江戸百景 王子音無川堰〔タイ〕世俗大滝ト唱-crd.jpg",
     "Большой водопад в Одзи", "Японская гравюра", 3),
    ("edo-kamata-plums", "NDL-DC 1303231-Utagawa Hiroshige-名所江戸百景 蒲田の梅園-crd.jpg",
     "Сливовый сад в Камате", "Японская гравюра", 3),
    ("edo-sazaido", "NDL-DC 1303276-Utagawa Hiroshige-名所江戸百景 五百羅漢さゞゐ堂-crd.jpg",
     "Павильон Садзаидо", "Японская гравюра", 3),
    ("edo-nihonbashi-street", "NDL-DC 1303248-Utagawa Hiroshige-名所江戸百景 日本橋通一丁目略図-crd.jpg",
     "Улица Нихонбаси", "Японская гравюра", 3),
    ("edo-surugacho", "NDL-DC 1303212-Utagawa Hiroshige-名所江戸百景 するかてふ-安政3-crd.jpg",
     "Квартал Суругатё", "Японская гравюра", 3),
    ("edo-yabu-lane", "NDL-DC 1303318-Utagawa Hiroshige-名所江戸百景 愛宕下藪小路-crd.jpg",
     "Переулок Ябу", "Японская гравюра", 3),
    ("edo-nippori", "NDL-DC 1303218-Utagawa Hiroshige-名所江戸百景 日暮里寺院の林泉-crd.jpg",
     "Храмовые сады в Ниппори", "Японская гравюра", 3),
    ("edo-hiroo", "NDL-DC 1303226-Utagawa Hiroshige-名所江戸百景 広尾ふる川-crd.jpg",
     "Река Фурукава в Хироо", "Японская гравюра", 3),
    ("edo-paulownia", "NDL-DC 1303252-Utagawa Hiroshige-名所江戸百景 赤坂桐畑-crd.jpg",
     "Сад павловний в Акасаке", "Японская гравюра", 3),
    ("edo-ryogoku", "NDL-DC 1303243-Utagawa Hiroshige-名所江戸百景 両国橋大川ばた-crd.jpg",
     "Мост Рёгоку", "Японская гравюра", 3),
    ("edo-ichigaya", "NDL-DC 1303245-Utagawa Hiroshige-名所江戸百景 市ケ谷八幡-crd.jpg",
     "Храм Хатимана в Итигае", "Японская гравюра", 3),
    ("edo-mama-maples", "Mama no momiji tekona no yashiro tsugihashi LCCN2008660944.jpg",
     "Клёны в Мама", "Японская гравюра", 3),
    ("edo-fudo-falls", "NDL-DC 1303251-Utagawa Hiroshige-名所江戸百景 王子不動之滝-crd.jpg",
     "Водопад Фудо", "Японская гравюра", 3),
    ("edo-oji-inari", "NDL-DC 1303222-Utagawa Hiroshige-名所江戸百景 王子稲荷の社-安政4-crd.jpg",
     "Храм Инари в Одзи", "Японская гравюра", 3),
    ("edo-five-pines", "Onagigawa gohonmatsu LCCN2009631876.jpg", "Пять сосен у канала Онаги",
     "Японская гравюра", 3),
    # Easy ones: OpenClipart drawings (CC0) of about 120 regions.
    ("autumn-forest", "openclipart:228043", "Осенний лес", "Природа", 2),
    ("cat-head", "openclipart:49477", "Кошка", "Животные", 2),
    ("igloo", "openclipart:177343", "Иглу", "Дома и города", 2),
    ("green-village", "openclipart:299596", "Зелёная деревня", "Дома и города", 2),
    ("flower-barrow", "openclipart:175892", "Тачка с цветами", "Цветы", 2),
    ("sun-landscape", "openclipart:174440", "Солнце над лесом", "Природа", 2),
    ("butterfly", "openclipart:5854", "Бабочка", "Животные", 2),
    ("pink-flowers", "openclipart:217229", "Розовые цветы", "Цветы", 2),
    ("lake-hills", "openclipart:281941", "Озеро среди холмов", "Природа", 2),
    ("lilies", "openclipart:217200", "Букет лилий", "Цветы", 2),
    ("easter-meadow", "openclipart:131827", "Весенний луг", "Природа", 2),
    ("sleeping-cat", "openclipart:49471", "Спящая кошка", "Животные", 2),
    ("thatched-cottage", "openclipart:311437", "Домик под соломой", "Дома и города", 2),
    ("lighthouse", "openclipart:167910", "Маяк", "Море и корабли", 2),
    ("sunny-grove", "openclipart:167542", "Солнечная роща", "Природа", 2),
    ("stone-house", "openclipart:299648", "Каменный домик", "Дома и города", 2),
    ("patterned-butterfly", "openclipart:9359", "Узорная бабочка", "Животные", 2),
    ("forest-camp", "openclipart:340815", "Лесная поляна", "Природа", 2),
    ("autumn-barn", "openclipart:168567", "Осенний сарай", "Дома и города", 2),
    ("summer-meadow", "openclipart:142357", "Летний луг", "Природа", 2),
    ("green-valley", "openclipart:340789", "Зелёная долина", "Природа", 2),
]
# Pictures whose own black outlines are kept (pbn.py --ink, level 1 for
# all of these unless INK_MORE has them at 2): prints and
# drawings with lines, where the outlines are the picture; chosen by
# looking at both kinds side by side (prints painted with a brush, like
# some of Koson's, get dark patches instead).
INK = {
    # Hokusai and Hiroshige (not Ono-shinden: its dark loads went black).
    "great-wave", "fuji-gotenyama", "fuji-mishima", "fuji-noboto", "fuji-tago",
    "fuji-mannen", "fuji-isawa", "fuji-sazai", "fuji-suwa", "fuji-senju", "fuji-katakura",
    "fuji-enoshima", "fuji-shichiri", "fuji-kawaguchi", "fuji-totomi",
    "plum-garden", "eagle-snow", "edo-koume", "edo-hachiman-garden", "edo-takinogawa",
    "edo-suijin", "edo-ekoin", "edo-great-waterfall", "edo-kamata-plums", "edo-sazaido",
    "edo-nihonbashi-street", "edo-surugacho", "edo-yabu-lane", "edo-nippori", "edo-hiroo",
    "edo-paulownia", "edo-ryogoku", "edo-ichigaya", "edo-mama-maples", "edo-fudo-falls",
    "edo-oji-inari", "edo-five-pines",
    # Koson's with lines (not the fox, the crow and blossom, the tit: their
    # brushed dark patches went black).
    "koson-cat-goldfish", "koson-owl-moon", "koson-lilies", "koson-snow-bridge",
    # OpenClipart drawings with black lines.
    "autumn-barn", "autumn-forest", "butterfly", "easter-meadow", "green-village",
    "green-valley", "summer-meadow", "sunny-grove", "lilies", "pink-flowers",
    "flower-barrow", "forest-camp", "thatched-cottage", "stone-house", "sun-landscape",
    "lighthouse",
}
# Of those, the ones with more of their dark lines kept (--ink 2).
INK_MORE = set()
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
        # Every built-in one with numbers to read without zooming far in.
        ink = (2 if slug in INK_MORE else 1) if slug in INK else 0
        pic = pbn.picture(Image.open(fetch(cache, name)), regions, colours, detail=detail,
                          crop=crop[0] if crop else None, min_radius=pbn.MIN_RADIUS_BIG,
                          ink=ink)
        pbn.write(pic, os.path.join(OUT, slug + ".svgz"),
                  {"mode": pbn.mode_name(True, ink), "name": title, "theme": theme,
                   "level": level, "source": name})
        print(slug, len(pic["regions"]), len(pic["palette"]))


if __name__ == "__main__":
    main()
