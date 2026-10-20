# SPDX-License-Identifier: GPL-2.0
"""Разделы галереи: in which sections the gallery shows the pictures.

Two orders, chosen above the gallery: by theme (Природа, Животные, ...),
easier first within each, or by difficulty (how many regions: Лёгкие,
Средние, ...), by theme within each. In both, the pictures begun come
first, in Продолжить (the last painted first; they stay in their own
section too), and the finished ones last, in Готовые (only there).

    sections(pictures, BY_THEME, state)
        -> [(heading, [(picture, note), ...]), ...]

state(picture) gives ("new" | "begun" | "done", when it was last
painted); a note is what the card says under the name that its heading
does not: the count of regions under a theme, the theme elsewhere.

A picture's theme: the built-in ones carry theme in their file; one
found on Wikidata gets it from its genre or what it depicts (theme_of);
own photos are Мои фотографии.
"""
NATURE, SEA, ANIMALS, FLOWERS = "Природа", "Море и корабли", "Животные", "Цветы"
PRINTS, TOWNS, PEOPLE, STILL = "Японская гравюра", "Дома и города", "Люди", "Натюрморт"
MY_PHOTOS, OTHER = "Мои фотографии", "Разное"
# The order of the theme sections.
THEMES = (MY_PHOTOS, NATURE, SEA, ANIMALS, FLOWERS, PRINTS, TOWNS, PEOPLE, STILL, OTHER)
# The themes of built-in pictures made before 4.5.
OLD_THEMES = {"Флот": SEA, "Военный флот": SEA, "Северная природа": NATURE, "Дома": TOWNS}
# Difficulty by the count of regions: up to so many, its section.
BANDS = ((150, "Лёгкие"), (350, "Средние"), (650, "Сложные"), (None, "Очень сложные"))
CONTINUE, FINISHED = "Продолжить", "Готовые"
BY_THEME, BY_DIFFICULTY = "theme", "difficulty"
ORDERS = ((BY_THEME, "По темам"), (BY_DIFFICULTY, "По сложности"))

# Wikidata: a painting's genre (P136), or else what it depicts (P180), as
# a theme; the first theme in WHICH_FIRST that matches wins (a ukiyo-e
# landscape is a print, a woman with a cat goes to the animals).
GENRES = {
    "Q185905": PRINTS,  # ukiyo-e
    "Q12303833": FLOWERS,  # flower painting
    "Q16875712": ANIMALS,  # animal art
    "Q158607": SEA,  # marine art
    "Q1935974": TOWNS, "Q166030": TOWNS,  # cityscape, veduta
    "Q191163": NATURE, "Q390001": NATURE,  # landscape, pastoral
    "Q170571": STILL,  # still life
    "Q134307": PEOPLE, "Q1551015": PEOPLE, "Q1047337": PEOPLE,  # portraits, genre art
    "Q742333": PEOPLE, "Q3374353": PEOPLE, "Q2864737": PEOPLE,  # history, battle, religious
}
DEPICTS = {
    "Q146": ANIMALS, "Q144": ANIMALS, "Q726": ANIMALS, "Q5113": ANIMALS, "Q729": ANIMALS,
    "Q506": FLOWERS,
    "Q165": SEA, "Q11446": SEA, "Q1075310": SEA, "Q35872": SEA,
    "Q3947": TOWNS, "Q79007": TOWNS, "Q515": TOWNS,
    "Q107425": NATURE, "Q4421": NATURE, "Q10884": NATURE, "Q23397": NATURE,
    "Q8502": NATURE, "Q4022": NATURE,
    "Q5": PEOPLE, "Q467": PEOPLE, "Q8441": PEOPLE, "Q7569": PEOPLE, "Q3010": PEOPLE,
    "Q3031": PEOPLE,
}
WHICH_FIRST = (PRINTS, FLOWERS, ANIMALS, SEA, TOWNS, NATURE, STILL, PEOPLE)


def _ids(claims, prop):
    found = []
    for st in claims.get(prop, []):
        value = st.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "id" in value:
            found.append(value["id"])
    return found


def theme_of(claims):
    """The theme of a Wikidata item from its claims (as wbgetentities
    gives them); OTHER when neither its genre nor what it depicts tells."""
    for prop, known in (("P136", GENRES), ("P180", DEPICTS)):
        themes = {known[q] for q in _ids(claims, prop) if q in known}
        for theme in WHICH_FIRST:
            if theme in themes:
                return theme
    return OTHER


def theme(pic):
    """The section a picture goes to by theme."""
    if pic["id"].startswith(("photo-", "wd-own-")):
        return MY_PHOTOS
    name = OLD_THEMES.get(pic.get("theme"), pic.get("theme"))
    # Pictures downloaded before 4.5 carry their artist there.
    return name if name in THEMES else OTHER


def difficulty(count):
    """The section of a picture of so many regions, by difficulty."""
    for most, name in BANDS:
        if most is None or count <= most:
            return name
    return BANDS[-1][1]


def plural(n, one, few, many):
    """n and the Russian word for so many: 1 область, 2 области, 5 областей."""
    if n % 10 == 1 and n % 100 != 11:
        word = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = few
    else:
        word = many
    return "%d %s" % (n, word)


def regions(n):
    return plural(n, "область", "области", "областей")


def sections(pictures, order, state):
    """The gallery's sections in order, those with no pictures left out:
    [(heading, [(picture, note)])]."""
    states = {p["id"]: state(p) for p in pictures}
    begun = [p for p in pictures if states[p["id"]][0] == "begun"]
    done = [p for p in pictures if states[p["id"]][0] == "done"]
    rest = [p for p in pictures if states[p["id"]][0] != "done"]
    recent = lambda p: -states[p["id"]][1]  # noqa: E731
    out = [(CONTINUE, [(p, theme(p)) for p in sorted(begun, key=recent)])]
    if order == BY_DIFFICULTY:
        groups = [name for _most, name in BANDS]
        group = lambda p: difficulty(p["count"])  # noqa: E731
        within = lambda p: (THEMES.index(theme(p)), p["count"], p["name"])  # noqa: E731
        note = theme
    else:
        groups = list(THEMES)
        group = theme
        within = lambda p: (p["count"], p["name"])  # noqa: E731
        note = lambda p: regions(p["count"])  # noqa: E731
    for name in groups:
        out.append((name, [(p, note(p)) for p in sorted(rest, key=within) if group(p) == name]))
    out.append((FINISHED, [(p, theme(p)) for p in sorted(done, key=recent)]))
    return [(heading, pics) for heading, pics in out if pics]
