#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Стенд генератора: the same images through variants of pbn.py's steps,
with numbers that say how near each comes to Happy Color, and a page to
see them side by side.

  python3 bench/bench.py CACHE OUT [--variants A,B,E,F] [--only SLUG,...] [--fetch]

CACHE holds the images that bench/images.txt lists (--fetch gets the
missing ones from Wikimedia Commons); OUT gets index.html and pictures.

Variants (B, C and D are experiments; what wins moves into pbn.py):
  A  pbn.py as it is.
  B  numpy and scipy only: an edge-preserving smoothing before k-means;
     a small region goes to the neighbour most like it (colour, and how
     weak the edge between them is), not just the longest border; merging
     goes on until the count is near the level's; numbers in the middle.
  C  as B, the smoothing by OpenCV's mean shift.
  D  OpenCV SLIC superpixels, coloured by k-means, then as B.
  E  as B, but neighbours of one colour join in every round of merging
     (pbn.merge joins them at the end and falls short of the count), so
     no merging again.
  F  as E, and no region thinner than MIN_RADIUS_F, for numbers that can
     be read without zooming far in.
The default is A,B,E,F (C and D lost the first comparison: OpenCV's mean
shift was little better than B for some 90 MB on the tablet, and SLIC
made a honeycomb across the shapes).

Numbers (per image and on average):
  regions     how many, against the level's target
  colours     used; "rare" are colours with at most two regions
  ΔE min      the two nearest palette colours (under ~10 is hard to tell)
  likeness    mean ΔE between the painted picture and the image (lower
              is truer)
  contours    of the image's strong edges, the share a border follows
              (within a pixel): borders along the shapes, not across
  r median    half-width where the number goes, in picture units (1000
              on the long side); small r needs zooming in
  r<5         share of regions whose number needs a large zoom
  slivers     regions thinner than 2.5 units
  points      outline points after simplifying (file size, drawing time)
  time        seconds here (the tablet is some 10-20 times slower)
"""
import argparse
import html
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from scipy import ndimage
from scipy.cluster.vq import kmeans2, vq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import pbn  # noqa: E402

try:
    import cv2
except ImportError:
    cv2 = None

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


# --- the steps ------------------------------------------------------------
def prepare(img, side):
    """pbn.reduce up to the small picture: turned, margin cut, brighter,
    shrunk, median 3."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    corner = Image.new("RGB", img.size, img.getpixel((0, 0)))
    box = ImageChops.difference(img, corner).convert("L").point(lambda v: v > 24 and 255).getbbox()
    if box and (box[2] - box[0]) * (box[3] - box[1]) > 0.3 * img.size[0] * img.size[1]:
        img = img.crop(box)
    img = ImageOps.autocontrast(img, cutoff=0.5, preserve_tone=True)
    img = ImageEnhance.Color(img).enhance(1.2)
    w, h = img.size
    size = (side, max(8, round(side * h / w))) if w >= h else (max(8, round(side * w / h)), side)
    return np.asarray(img.resize(size, Image.LANCZOS).filter(ImageFilter.MedianFilter(3)))


def guided(rgb, radius=3, eps=0.0025, passes=1):
    """Self-guided filter on each channel: flat where the picture varies
    less than eps, edges kept (He et al.; box filters only)."""
    out = rgb.astype(np.float32) / 255
    size = 2 * radius + 1
    for _ in range(passes):
        res = np.empty_like(out)
        for c in range(3):
            i = out[:, :, c]
            mean = ndimage.uniform_filter(i, size)
            var = ndimage.uniform_filter(i * i, size) - mean * mean
            a = var / (var + eps)
            b = mean - a * mean
            res[:, :, c] = ndimage.uniform_filter(a, size) * i + ndimage.uniform_filter(b, size)
        out = res
    return (out.clip(0, 1) * 255 + 0.5).astype(np.uint8)


def mean_shift(rgb, sp=10, sr=18):
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return cv2.cvtColor(cv2.pyrMeanShiftFiltering(bgr, sp, sr), cv2.COLOR_BGR2RGB)


def palette_of(pixels, colours, weights=None):
    """pbn.reduce's k-means in Lab and its merging of colours too alike:
    (centre index of each pixel mapped to kept colours, kept count)."""
    rng = np.random.default_rng(1)
    if weights is None:
        sample = pixels[rng.choice(len(pixels), min(len(pixels), 20000), replace=False)]
    else:
        pick = rng.choice(len(pixels), 20000, p=weights / weights.sum())
        sample = pixels[pick]
    centres, _ = kmeans2(sample, colours + 6, minit="++", seed=rng, iter=20)
    idx, _ = vq(pixels, centres)
    counts = np.bincount(idx, minlength=len(centres)).astype(float)
    if weights is not None:
        counts = np.bincount(idx, weights, minlength=len(centres))
    keep, to = [], np.zeros(len(centres), np.int64)
    for i in np.argsort(-counts):
        if not counts[i]:
            continue
        near = [k for k, j in enumerate(keep) if np.linalg.norm(centres[i] - centres[j]) < 9]
        if near or len(keep) == colours:
            to[i] = int(np.argmin([np.linalg.norm(centres[i] - centres[j]) for j in keep]))
        else:
            to[i] = len(keep)
            keep.append(i)
    return to[idx], len(keep)


def quantise(rgb, colours, detail):
    h, w, _ = rgb.shape
    flat = rgb.reshape(-1, 3)
    idx, n = palette_of(pbn.lab(flat), colours)
    img_idx = Image.fromarray(idx.reshape(h, w).astype(np.uint8), "L")
    if detail > 1:
        img_idx = img_idx.filter(ImageFilter.ModeFilter(detail))
    return np.asarray(img_idx).astype(np.int32), n


def superpixels(rgb, regions, colours):
    """SLICO superpixels (about six per region wanted), each one colour by
    k-means over their mean Lab colours."""
    h, w, _ = rgb.shape
    size = max(6, int(round((w * h / (6 * regions)) ** 0.5)))
    lab8 = cv2.cvtColor(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2LAB)
    slic = cv2.ximgproc.createSuperpixelSLIC(lab8, cv2.ximgproc.SLICO, size, 10.0)
    slic.iterate(10)
    slic.enforceLabelConnectivity(25)
    sp = slic.getLabels()
    n = sp.max() + 1
    pix = pbn.lab(rgb.reshape(-1, 3))
    area = np.bincount(sp.ravel(), minlength=n).astype(float)
    mean = np.stack([np.bincount(sp.ravel(), pix[:, k], n) for k in range(3)], 1) / area.clip(1)[:, None]
    idx, kept = palette_of(mean[area > 0], colours, area[area > 0])
    of_sp = np.zeros(n, np.int64)
    of_sp[area > 0] = idx
    return of_sp[sp].astype(np.int32), kept


def mean_colours(idx, rgb, n):
    flat = idx.ravel()
    total = np.bincount(flat, minlength=n).clip(1)
    return np.stack([np.bincount(flat, rgb.reshape(-1, 3)[:, k].astype(float), n) / total
                     for k in range(3)], 1)


def edges(rgb):
    """Gradient strength of the picture's lightness, 0..1."""
    light = pbn.lab(rgb.reshape(-1, 3))[:, 0].reshape(rgb.shape[:2])
    light = ndimage.gaussian_filter(light, 1)
    g = np.hypot(ndimage.sobel(light, 0), ndimage.sobel(light, 1))
    return (g / (np.percentile(g, 99) + 1e-6)).clip(0, 1)


def best_alike(labels, n, small, colour_lab, strength):
    """For each small region the neighbour to join: long shared border,
    alike colour, weak edge between; -1 for none."""
    a = np.concatenate((labels[:, :-1].ravel(), labels[:-1, :].ravel()))
    b = np.concatenate((labels[:, 1:].ravel(), labels[1:, :].ravel()))
    ga = np.concatenate((np.maximum(strength[:, :-1], strength[:, 1:]).ravel(),
                         np.maximum(strength[:-1, :], strength[1:, :]).ravel()))
    diff = a != b
    a, b, ga = a[diff], b[diff], ga[diff]
    src, dst, g = np.concatenate((a, b)), np.concatenate((b, a)), np.concatenate((ga, ga))
    want = small[src]
    keys, inv, counts = np.unique(src[want].astype(np.int64) * n + dst[want],
                                  return_inverse=True, return_counts=True)
    edge = np.bincount(inv, g[want], len(keys)) / counts
    src, dst = keys // n, keys % n
    de = np.linalg.norm(colour_lab[src] - colour_lab[dst], axis=1)
    score = counts * np.exp(-de / 12) * (1 - 0.8 * edge)
    order = np.lexsort((-score, src))
    src, dst = src[order], dst[order]
    first = np.ones(len(src), bool)
    first[1:] = src[1:] != src[:-1]
    best = np.full(n, -1, np.int64)
    best[src[first]] = dst[first]
    return best


def merge_alike(labels, colour_of, palette_lab, strength, regions, min_area, min_radius):
    """pbn.merge with best_alike instead of the longest border."""
    thin_rounds = 0
    while True:
        n = len(colour_of)
        area = np.bincount(labels.ravel(), minlength=n)
        small = area < min_area
        if n > regions:
            small[np.argsort(area)[:max(1, (n - regions) // 4)]] = True
        if not small.any():
            small = pbn.radii(labels, pbn.inner_distance(labels), n) < min_radius
            if not small.any() or thin_rounds == 4:
                return pbn.components(colour_of[labels], colour_of.max() + 1)
            thin_rounds += 1
        best = best_alike(labels, n, small, palette_lab[colour_of], strength)
        parent = np.arange(n)
        go = small & (best >= 0)
        parent[go] = best[go]
        ids = np.arange(n)
        for _ in range(64):
            nxt = parent[parent]
            loop = (nxt == ids) & (parent != ids)
            loop &= (area > area[parent]) | ((area == area[parent]) & (ids > parent))
            parent[loop] = ids[loop]
            nxt = parent[parent]
            if (nxt == parent).all():
                break
            parent = nxt
        roots, new = np.unique(parent, return_inverse=True)
        labels = new[labels].astype(np.int32)
        colour_of = colour_of[roots]


def border_pairs(labels, strength):
    """Every pair of 4-neighbour pixels in different regions: (a, b, edge
    strength there)."""
    a = np.concatenate((labels[:, :-1].ravel(), labels[:-1, :].ravel()))
    b = np.concatenate((labels[:, 1:].ravel(), labels[1:, :].ravel()))
    g = np.concatenate((np.maximum(strength[:, :-1], strength[:, 1:]).ravel(),
                        np.maximum(strength[:-1, :], strength[1:, :]).ravel()))
    diff = a != b
    return a[diff], b[diff], g[diff]


def choose(a, b, g, n, small, colour_lab, alike):
    """For each small region the neighbour to join (-1 for none): the
    longest border, or (alike) long border, alike colour, weak edge."""
    src, dst, g = np.concatenate((a, b)), np.concatenate((b, a)), np.concatenate((g, g))
    want = small[src]
    keys, inv, counts = np.unique(src[want].astype(np.int64) * n + dst[want],
                                  return_inverse=True, return_counts=True)
    src, dst = keys // n, keys % n
    score = counts.astype(float)
    if alike:
        edge = np.bincount(inv, g[want], len(keys)) / counts
        de = np.linalg.norm(colour_lab[src] - colour_lab[dst], axis=1)
        score *= np.exp(-de / 12) * (1 - 0.8 * edge)
    order = np.lexsort((-score, src))
    src, dst = src[order], dst[order]
    first = np.ones(len(src), bool)
    first[1:] = src[1:] != src[:-1]
    best = np.full(n, -1, np.int64)
    best[src[first]] = dst[first]
    return best


def roots_of(parent):
    """Pointer jumping until every region points at its root."""
    for _ in range(64):
        nxt = parent[parent]
        if (nxt == parent).all():
            break
        parent = nxt
    return parent


def merge_fused(labels, colour_of, palette_lab, strength, regions, min_area, min_radius,
                alike=True):
    """pbn.merge, but neighbours that become one colour join in every
    round, so the count it aims at is the count it ends with (pbn.merge
    joins them only at the end, and falls short)."""
    thin_rounds = 0
    while True:
        n = len(colour_of)
        area = np.bincount(labels.ravel(), minlength=n)
        small = area < min_area
        if n > regions:
            small[np.argsort(area)[:max(1, (n - regions) // 4)]] = True
        if not small.any():
            small = pbn.radii(labels, pbn.inner_distance(labels), n) < min_radius
            if not small.any() or thin_rounds == 4:
                return labels, colour_of
            thin_rounds += 1
        a, b, g = border_pairs(labels, strength)
        best = choose(a, b, g, n, small, palette_lab[colour_of], alike)
        parent = np.arange(n)
        go = small & (best >= 0)
        parent[go] = best[go]
        ids = np.arange(n)
        for _ in range(64):
            nxt = parent[parent]
            loop = (nxt == ids) & (parent != ids)
            loop &= (area > area[parent]) | ((area == area[parent]) & (ids > parent))
            parent[loop] = ids[loop]
            nxt = parent[parent]
            if (nxt == parent).all():
                break
            parent = nxt
        # Then neighbours now of one colour become one region.
        a, b = parent[a], parent[b]
        same = (a != b) & (colour_of[a] == colour_of[b])
        a, b = a[same], b[same]
        for _ in range(64):
            if not len(a):
                break
            low = np.minimum(parent[a], parent[b])
            np.minimum.at(parent, parent[a], low)
            np.minimum.at(parent, parent[b], low)
            parent = roots_of(parent)
            if (parent[a] == parent[b]).all():
                break
        roots, new = np.unique(parent, return_inverse=True)
        labels = new[labels].astype(np.int32)
        colour_of = colour_of[roots]


def label_points(labels, n, middle):
    """Where each number goes: (rows, cols, radius). middle: among the
    widest pixels the one nearest the region's centre, else pbn's first."""
    dist = pbn.inner_distance(labels)
    radius = pbn.radii(labels, dist, n)
    flat = labels.ravel()
    h, w = labels.shape
    if not middle:
        top = np.flatnonzero(dist.ravel() == radius[flat])
        _, first = np.unique(flat[top], return_index=True)
        pick = top[first]
    else:
        top = np.flatnonzero(dist.ravel() >= radius[flat] * 0.9)
        ys, xs = np.divmod(top, w)
        area = np.bincount(flat, minlength=n).clip(1)
        allys, allxs = np.divmod(np.arange(h * w), w)
        cy = np.bincount(flat, allys, n) / area
        cx = np.bincount(flat, allxs, n) / area
        lab_top = flat[top]
        # Among the near-widest, the one nearest the centre, but not
        # giving up more than a tenth of the width.
        far = (ys - cy[lab_top]) ** 2 + (xs - cx[lab_top]) ** 2
        order = np.lexsort((far, lab_top))
        first = np.ones(len(order), bool)
        first[1:] = lab_top[order][1:] != lab_top[order][:-1]
        pick = top[order[first]]
    rows, cols = np.divmod(pick, w)
    return rows, cols, dist.ravel()[pick]


def run(variant, img, level):
    regions, colours, detail = pbn.LEVELS[level]
    t = {}
    start = time.monotonic()
    rgb = prepare(img, pbn.SIDE)
    t["prepare"] = time.monotonic() - start
    lap = time.monotonic()
    if variant == "A":
        idx, n_col = pbn.reduce(img, pbn.SIDE, colours, detail)
        n_col = len(n_col)
    elif variant in ("B", "C", "E", "F"):
        smooth = mean_shift(rgb) if variant == "C" else guided(rgb)
        idx, n_col = quantise(smooth, colours, detail)
    else:
        idx, n_col = superpixels(rgb, regions, colours)
    t["colours"] = time.monotonic() - lap
    lap = time.monotonic()
    palette = mean_colours(idx, rgb, n_col)
    labels, colour_of = pbn.components(idx, n_col)
    h, w = labels.shape
    min_area = w * h / regions / 30
    if variant == "A":
        labels, colour_of = pbn.merge(labels, colour_of, regions, min_area, 2.5)
    elif variant in ("E", "F"):
        strength = edges(rgb)
        palette_lab = pbn.lab(np.clip(palette + 0.5, 0, 255).astype(np.uint8))
        labels, colour_of = merge_fused(labels, colour_of, palette_lab, strength, regions,
                                        min_area, 2.5 if variant == "E" else MIN_RADIUS_F)
    else:
        strength = edges(rgb)
        palette_lab = pbn.lab(np.clip(palette + 0.5, 0, 255).astype(np.uint8))
        start_labels, start_colours = labels, colour_of
        labels, colour_of = merge_alike(labels, colour_of, palette_lab, strength,
                                        regions, min_area, 2.5)
        # Neighbours of one colour join at the end, so the count falls
        # short; again with a target raised by as much, a few times.
        aim = regions
        for _ in range(3):
            if len(colour_of) >= 0.9 * regions:
                break
            aim = int(aim * regions / max(1, len(colour_of)))
            labels, colour_of = merge_alike(start_labels, start_colours, palette_lab, strength,
                                            aim, min_area, 2.5)
    t["regions"] = time.monotonic() - lap
    lap = time.monotonic()
    n = len(colour_of)
    rows, cols, radius = label_points(labels, n, variant != "A")
    points = 0
    for xs, ys, _left, _right in pbn.trace(labels):
        closed = len(xs) > 2 and xs[0] == xs[-1] and ys[0] == ys[-1]
        points += len(pbn.simplify(pbn.smooth(xs, ys, closed), 0.25))
    t["outlines"] = time.monotonic() - lap
    t["total"] = time.monotonic() - start
    return {"rgb": rgb, "labels": labels, "colour_of": colour_of, "palette": palette,
            "rows": rows, "cols": cols, "radius": radius, "points": points, "time": t,
            "target": regions}


# --- measuring and drawing -------------------------------------------------
def measure(res):
    labels, colour_of, palette = res["labels"], res["colour_of"], res["palette"]
    rgb = res["rgb"]
    n = len(colour_of)
    used = np.unique(colour_of)
    pal_lab = pbn.lab(np.clip(palette + 0.5, 0, 255).astype(np.uint8))[used]
    d = np.linalg.norm(pal_lab[:, None] - pal_lab[None], axis=2)
    d[np.arange(len(used)), np.arange(len(used))] = 1e9
    painted = np.clip(palette[colour_of[labels]] + 0.5, 0, 255).astype(np.uint8)
    like = np.linalg.norm(pbn.lab(painted.reshape(-1, 3)) - pbn.lab(rgb.reshape(-1, 3)), axis=1).mean()
    border = np.zeros(labels.shape, bool)
    border[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    border[1:, :] |= labels[1:, :] != labels[:-1, :]
    strength = edges(rgb)
    strong = strength > np.percentile(strength, 90)
    near = ndimage.binary_dilation(border, iterations=1)
    per_colour = np.bincount(colour_of, minlength=palette.shape[0])[used]
    r = res["radius"]
    return {"regions": n, "target": res["target"], "colours": len(used),
            "rare": int((per_colour <= 2).sum()), "de_min": float(d.min()),
            "likeness": float(like), "contours": float(near[strong].mean()),
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
    img = Image.fromarray(blank)
    pen = ImageDraw.Draw(img)
    fonts = {}
    for i in range(len(colour_of)):
        size = int(min(30, res["radius"][i] * 1.2))
        if size < 7:
            continue
        f = fonts.setdefault(size, font(size))
        pen.text((int(res["cols"][i]), int(res["rows"][i])), str(number[int(colour_of[i])]),
                 fill=(90, 90, 90), font=f, anchor="mm")
    img.save(out_player, quality=88)


# Variant F: no region thinner than this (picture units), so that its
# number can be read without zooming far in.
MIN_RADIUS_F = 3.5
NAMES = {"A": "A · как сейчас", "B": "B · numpy: края и цвет",
         "E": "E · B, слияние по ходу", "F": "F · E, номера крупнее",
         "C": "C · OpenCV mean shift", "D": "D · OpenCV SLIC"}
COLUMNS = [("regions", "области", "%d"), ("colours", "цвета", "%d"), ("rare", "редкие", "%d"),
           ("de_min", "ΔE min", "%.1f"), ("likeness", "сходство ΔE↓", "%.1f"),
           ("contours", "по контурам↑", "%.0f%%"), ("r_median", "r медиана↑", "%.1f"),
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
    args.add_argument("--variants", default="A,B,E,F")
    args.add_argument("--only", default="")
    args.add_argument("--fetch", action="store_true")
    opts = args.parse_args()
    variants = [v for v in opts.variants.split(",") if v in NAMES]
    if cv2 is None:
        variants = [v for v in variants if v not in ("C", "D")]
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
            res = run(v, img, level)
            per[v] = measure(res)
            draw(res, os.path.join(opts.out, "%s-%s-painted.jpg" % (slug, v)),
                 os.path.join(opts.out, "%s-%s-player.png" % (slug, v)))
            if v == variants[0]:
                Image.fromarray(res["rgb"]).save(os.path.join(opts.out, slug + "-orig.jpg"), quality=88)
            m = per[v]
            print("%-14s %s  %4d/%-4d regions  %2d colours  contours %3.0f%%  r~%4.1f  "
                  "r<5 %3.0f%%  like %4.1f  %5.1f s" % (
                      slug, v, m["regions"], m["target"], m["colours"], 100 * m["contours"],
                      m["r_median"], 100 * m["r_small"], m["likeness"], m["time"]), flush=True)
        results[slug] = per
        page(opts.out, results, variants)


if __name__ == "__main__":
    main()
