#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Стенд генератора: the same images through pbn.py in each of its modes,
with numbers that say how near each comes to Happy Color, and a page to
see them side by side.

  python3 bench/bench.py CACHE OUT [--variants normal,big,ink,fast] [--only SLUG,...]
                         [--fetch] [--fast PBN_CLI]

CACHE holds the images that bench/images.txt lists (--fetch gets the
missing ones from Wikimedia Commons); OUT gets index.html and pictures.
Modes: normal; big (--big-numbers: no region too thin for a number read
without zooming far in); ink and ink2 (big and --ink or --more-ink: the
picture's own black outlines kept, few or more); fast, another
generator to measure against: fast-paint-by-numbers (github.com/ianho7,
MIT, drake7707's algorithm in Rust), its pbn-cli given by --fast, on the
same shrunk image, aiming at the level's regions and colours, its
regions measured as pbn.py's are (the numbers placed by label_points).

What it showed (October 2026, 11 images, against pbn.py before 4.3):
smoothing that keeps edges and joining the neighbour most alike (colour,
a weak edge) made borders follow the shapes (48% to 55% of strong edges)
and the picture truer (ΔE 7.3 to 6.9), and joining same-coloured
neighbours in every round kept the time (2.3 s to 2.2 s here). OpenCV's
mean shift was little better (56%) for some 90 MB on the tablet, SLIC
superpixels worse (40%, a honeycomb across the shapes); so pbn.py has
neither. Big numbers: 46% to 30% of numbers needing a large zoom, for a
quarter fewer regions. Ink: on prints with lines, 66% to 78%. Details
(a cat's pupil and iris were lost, so small regions far in colour from
where they would go now stay): borders along the shapes 51% to 56%
with big numbers, likeness 7.1 to 6.8, for more small numbers (31% to
43% need a large zoom).

October 2026, 21 images (snow and white walls added): fast-paint-by-numbers
took half the time (10 s against 21 s on the tablet, 1.3 s against 2.6 s
here) but was further from the image (ΔE 8.9 against 7.1), its borders
less along the shapes (41% against 58%), its palette with colours hardly
told apart (ΔE min 3.5) and smooth skies in bands; it kept more of the
faint shading of light parts (33% against 26%), which pbn.py lost by
joining light colours under ΔE 9 apart. Light colours divided by an edge
now stay down to EDGED_DE, and the guided filter flattens light parts
less (faint 26% to 30%, likeness 7.1 to 6.9, numbers needing a large zoom
45% to 39%, the tablet's time 20.6 to 21.7 s). Splitting large regions
to reach the count was not done: what is lost are strips too thin for a
number, and a region split in two of one colour only adds taps.

Numbers (per image and on average):
  regions     how many, against the level's target
  colours     used; "rare" are colours with at most two regions
  ΔE min      the two nearest palette colours (under ~10 is hard to tell)
  likeness    mean ΔE between the painted picture and the image (lower
              is truer)
  contours    of the image's strong edges, the share a border follows
              (within a pixel): borders along the shapes, not across
  faint       the same for the faint edges of light parts (the 75th to
              90th percentile of edge strength where L* is over 70): the
              shading of white walls and snow, which strong edges miss
  r median    half-width where the number goes, in picture units (1000
              on the long side); small r needs zooming in
  r<5         share of regions whose number needs a large zoom
  slivers     regions thinner than 2.5 units
  points      outline points (file size, drawing time)
  time        seconds here (the tablet is some 7-9 times slower)
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import pbn  # noqa: E402

AGENT = "haltia-paint-bench (https://github.com/haltia-de/paint)"


def images():
    out = []
    with open(os.path.join(HERE, "images.txt")) as fh:
        for line in fh:
            if line.strip() and not line.startswith("#"):
                slug, level, name = (p.strip() for p in line.split("|"))
                out.append((slug, int(level), name))
    return out


def fetch(cache, slug, name):
    path = os.path.join(cache, slug + ".jpg")
    if os.path.exists(path) or not name.endswith((".jpg", ".JPG", ".jpeg", ".png")):
        return path
    url = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
           + urllib.parse.quote(name) + "?width=1200")
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    with open(path, "wb") as fh:
        fh.write(data)
    time.sleep(2)
    return path


# --- the modes ---------------------------------------------------------------
MODES = {"normal": {}, "big": {"min_radius": pbn.MIN_RADIUS_BIG},
         "ink": {"min_radius": pbn.MIN_RADIUS_BIG, "ink": 1},
         "ink2": {"min_radius": pbn.MIN_RADIUS_BIG, "ink": 2}}
NAMES = {"normal": "обычные номера", "big": "крупные номера", "ink": "крупные + контуры мало",
         "ink2": "крупные + контуры много", "fast": "fast-paint-by-numbers"}
INK = pbn.INK
# fast-paint-by-numbers' settings: its defaults (drake7707's), but for the
# count of regions and colours.
FAST = {"random_seed": 0, "kmeans_min_delta": 1.0, "kmeans_color_space": "rgb",
        "color_restrictions": [], "color_aliases": {}, "narrow_pixel_cleanup_runs": 3,
        "remove_facets_smaller_than": 20, "remove_facets_from_large_to_small": True,
        "border_smoothing_passes": 2,
        "resize": {"enabled": False, "max_width": 1024, "max_height": 1024},
        "show_labels": False, "show_borders": False, "fill_facets": True,
        "log_level": "error", "debug_flags": []}


def run_fast(cli, img, level):
    regions, colours, _detail = pbn.LEVELS[level]
    rgb = pbn.shrink(img, pbn.SIDE)
    with tempfile.TemporaryDirectory() as tmp:
        Image.fromarray(rgb).save(os.path.join(tmp, "in.png"))
        with open(os.path.join(tmp, "config.json"), "w") as fh:
            json.dump(dict(FAST, kmeans_clusters=colours, maximum_number_of_facets=regions), fh)
        subprocess.run([cli, "-i", os.path.join(tmp, "in.png"), "-o", os.path.join(tmp, "out.svg"),
                        "-c", os.path.join(tmp, "config.json"), "--format", "svg,debug.json",
                        "--no-resize", "--quiet"], check=True)
        with open(os.path.join(tmp, "out.debug.json")) as fh:
            out = json.load(fh)
    # Its own time, not writing the debug output.
    total = out["metrics"]["stage_timings"]["total_ms"] / 1000
    h, w = rgb.shape[:2]
    ids, labels = np.unique(np.array(out["debug"]["facet_map"], np.int64), return_inverse=True)
    labels = labels.reshape(h, w)
    colour = {f["id"]: f["color_index"] for f in out["facets_summary"]}
    colour_of = np.array([colour[int(i)] for i in ids])
    palette = np.array([p["color"] for p in sorted(out["palette"], key=lambda p: p["index"])], float)
    rows, cols, radius = pbn.label_points(labels, len(ids))
    points = len(re.findall(r"[MQ] ", out["svg"]))
    return {"rgb": rgb, "labels": labels, "colour_of": colour_of, "palette": palette,
            "ink": None, "rows": rows, "cols": cols, "radius": radius, "points": points,
            "target": regions, "time": {"total": total}}


def run(mode, img, level, fast=None):
    if mode == "fast":
        return run_fast(fast, img, level)
    regions, colours, detail = pbn.LEVELS[level]
    timing = []
    start = time.monotonic()
    pic = pbn.picture(img, regions, colours, detail=detail, timing=timing, raster=True,
                      **MODES[mode])
    total = time.monotonic() - start
    rgb, labels, colour_of, keep, ink, rows, cols, radius = pic["raster"]
    points = sum(len(ring) for _n, _l, outline in pic["regions"] for ring in outline)
    return {"rgb": rgb, "labels": labels, "colour_of": colour_of,
            "palette": np.array(keep, float), "ink": ink, "rows": rows, "cols": cols,
            "radius": radius, "points": points, "target": regions,
            "time": dict(timing, total=total)}


# --- measuring and drawing -------------------------------------------------
def measure(res):
    labels, colour_of, palette = res["labels"], res["colour_of"], res["palette"]
    rgb = res["rgb"]
    real = colour_of != res["ink"]
    n = int(real.sum())
    used = np.unique(colour_of[real])
    pal_lab = pbn.lab(np.clip(palette + 0.5, 0, 255).astype(np.uint8))[used]
    d = np.linalg.norm(pal_lab[:, None] - pal_lab[None], axis=2)
    d[np.arange(len(used)), np.arange(len(used))] = 1e9
    painted = np.clip(palette[colour_of[labels]] + 0.5, 0, 255).astype(np.uint8)
    like = np.linalg.norm(pbn.lab(painted.reshape(-1, 3)) - pbn.lab(rgb.reshape(-1, 3)), axis=1).mean()
    border = np.zeros(labels.shape, bool)
    border[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    border[1:, :] |= labels[1:, :] != labels[:-1, :]
    light = pbn.lightness(rgb)
    strength = pbn.edges(light)
    strong = strength > np.percentile(strength, 90)
    faint = (strength > np.percentile(strength, 75)) & ~strong & (light > 70)
    near = ndimage.binary_dilation(border, iterations=1)
    per_colour = np.bincount(colour_of[real], minlength=palette.shape[0])[used]
    r = res["radius"][real]
    return {"regions": n, "target": res["target"], "colours": len(used),
            "rare": int((per_colour <= 2).sum()), "de_min": float(d.min()),
            "likeness": float(like), "contours": float(near[strong].mean()),
            "faint": float(near[faint].mean()) if faint.any() else 0.0,
            "r_median": float(np.median(r)), "r_small": float((r < 5).mean()),
            "slivers": int((r < 2.5).sum()), "points": res["points"],
            "time": res["time"]["total"], "times": res["time"]}


def font(size):
    for path in ("/usr/share/fonts/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw(res, out_painted, out_player):
    labels, colour_of, palette = res["labels"], res["colour_of"], res["palette"]
    border = np.zeros(labels.shape, bool)
    border[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    border[1:, :] |= labels[1:, :] != labels[:-1, :]
    painted = np.clip(palette[colour_of[labels]] + 0.5, 0, 255).astype(np.uint8)
    painted[border] = (painted[border] * 0.55).astype(np.uint8)
    Image.fromarray(painted).save(out_painted, quality=88)
    # What the player starts with: pale grey, outlines, numbers light to dark.
    used = sorted(np.unique(colour_of).tolist(),
                  key=lambda c: -(0.299 * palette[c][0] + 0.587 * palette[c][1] + 0.114 * palette[c][2]))
    number = {c: k + 1 for k, c in enumerate(used)}
    blank = np.full(labels.shape + (3,), 246, np.uint8)
    blank[border] = (150, 150, 150)
    if res["ink"] is not None:
        blank[colour_of[labels] == res["ink"]] = INK
    img = Image.fromarray(blank)
    pen = ImageDraw.Draw(img)
    fonts = {}
    for i in range(len(colour_of)):
        size = int(min(30, res["radius"][i] * 1.2))
        if size < 7 or colour_of[i] == res["ink"]:
            continue
        f = fonts.setdefault(size, font(size))
        pen.text((int(res["cols"][i]), int(res["rows"][i])), str(number[int(colour_of[i])]),
                 fill=(90, 90, 90), font=f, anchor="mm")
    img.save(out_player, quality=88)


COLUMNS = [("regions", "области", "%d"), ("colours", "цвета", "%d"), ("rare", "редкие", "%d"),
           ("de_min", "ΔE min", "%.1f"), ("likeness", "сходство ΔE↓", "%.1f"),
           ("contours", "по контурам↑", "%.0f%%"), ("faint", "светлые грани↑", "%.0f%%"),
           ("r_median", "r медиана↑", "%.1f"),
           ("r_small", "r<5↓", "%.0f%%"), ("slivers", "осколки↓", "%d"),
           ("points", "точки", "%d"), ("time", "время, с", "%.1f")]


def cell(key, fmt, m):
    v = m[key] * 100 if fmt.endswith("%%") else m[key]
    text = fmt % v
    if key == "regions":
        text += " / %d" % m["target"]
    return text


def page(out, results, variants):
    rows = []
    avg = {}
    for v in variants:
        ms = [r[v] for r in results.values() if v in r]
        avg[v] = {k: float(np.mean([m[k] for m in ms])) for k, _l, _f in COLUMNS + [("target", "", "")]}
    head = "".join("<th>%s</th>" % html.escape(label) for _k, label, _f in COLUMNS)
    rows.append("<h2>В среднем</h2><table><tr><th></th>%s</tr>" % head)
    for v in variants:
        rows.append("<tr><td>%s</td>%s</tr>" % (NAMES[v], "".join(
            "<td>%s</td>" % cell(k, f, avg[v]) for k, _l, f in COLUMNS)))
    rows.append("</table>")
    for slug, per in results.items():
        rows.append("<h2>%s</h2><table><tr><th></th>%s</tr>" % (html.escape(slug), head))
        for v in variants:
            if v in per:
                rows.append("<tr><td>%s</td>%s</tr>" % (NAMES[v], "".join(
                    "<td>%s</td>" % cell(k, f, per[v]) for k, _l, f in COLUMNS)))
        rows.append("</table><div class='grid'>")
        rows.append("<figure><img src='%s-orig.jpg'><figcaption>картинка</figcaption></figure>" % slug)
        for v in variants:
            if v in per:
                rows.append("<figure><img src='%s-%s-painted.jpg' data-player='%s-%s-player.png'>"
                            "<figcaption>%s</figcaption></figure>" % (slug, v, slug, v, NAMES[v]))
        rows.append("</div>")
    doc = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Стенд генератора</title><style>
:root { --bg:#f6f5f2; --fg:#1f2328; --muted:#6b6f76; --line:#d9d7d2; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#16181b; --fg:#e7e7e4; --muted:#9a9ea5; --line:#33363b; } }
body { background:var(--bg); color:var(--fg); font:15px/1.45 system-ui, sans-serif; margin:0; padding:16px; }
main { max-width:1500px; margin:auto; }
table { border-collapse:collapse; margin:8px 0 12px; font-variant-numeric:tabular-nums; display:block; overflow-x:auto; }
th, td { border-bottom:1px solid var(--line); padding:4px 10px; text-align:right; white-space:nowrap; }
th:first-child, td:first-child { text-align:left; }
th { color:var(--muted); font-weight:500; }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:10px; }
figure { margin:0; } img { width:100%%; border:1px solid var(--line); cursor:zoom-in; }
figcaption { color:var(--muted); font-size:13px; }
.note { color:var(--muted); max-width:70ch; }
</style></head><body><main>
<h1>Стенд генератора</h1>
<p class="note">Нажатие на раскраску переключает её вид: закрашенная ↔ как в начале игры (контуры и номера).
Стрелка ↑/↓ — в какую сторону лучше. Время — на ПК в Alpine; на планшете в 10–20 раз дольше.</p>
%s
</main><script>
document.querySelectorAll("img[data-player]").forEach(function (img) {
  img.addEventListener("click", function () {
    var other = img.dataset.player; img.dataset.player = img.getAttribute("src"); img.src = other;
  });
});
</script></body></html>""" % "\n".join(rows)
    with open(os.path.join(out, "index.html"), "w") as fh:
        fh.write(doc)


def main():
    args = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    args.add_argument("cache")
    args.add_argument("out")
    args.add_argument("--variants", default="normal,big,ink")
    args.add_argument("--only", default="")
    args.add_argument("--fetch", action="store_true")
    args.add_argument("--fast", help="fast-paint-by-numbers' pbn-cli, for the fast variant")
    opts = args.parse_args()
    variants = [v for v in opts.variants.split(",") if v in NAMES and (v != "fast" or opts.fast)]
    os.makedirs(opts.out, exist_ok=True)
    results = {}
    for slug, level, name in images():
        if opts.only and slug not in opts.only.split(","):
            continue
        path = fetch(opts.cache, slug, name) if opts.fetch else os.path.join(opts.cache, slug + ".jpg")
        if not os.path.exists(path):
            print("missing", path)
            continue
        img = Image.open(path)
        img.load()
        per = {}
        for v in variants:
            res = run(v, img, level, opts.fast)
            per[v] = measure(res)
            draw(res, os.path.join(opts.out, "%s-%s-painted.jpg" % (slug, v)),
                 os.path.join(opts.out, "%s-%s-player.png" % (slug, v)))
            if v == variants[0]:
                Image.fromarray(res["rgb"]).save(os.path.join(opts.out, slug + "-orig.jpg"), quality=88)
            m = per[v]
            print("%-14s %s  %4d/%-4d regions  %2d colours  contours %3.0f%%  faint %3.0f%%  r~%4.1f  "
                  "r<5 %3.0f%%  like %4.1f  %5.1f s" % (
                      slug, v, m["regions"], m["target"], m["colours"], 100 * m["contours"], 100 * m["faint"],
                      m["r_median"], 100 * m["r_small"], m["likeness"], m["time"]), flush=True)
        results[slug] = per
        page(opts.out, results, variants)


if __name__ == "__main__":
    main()
