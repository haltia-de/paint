#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Paint by number in regions: a picture split into numbered areas.

  pbn.py [--level 2|3|4|5] [--big-numbers] [--ink|--more-ink] [--set name=...] [--progress] IMAGE OUT.svgz

A painting becomes a map of regions, one colour number each, written as
SVG: one <path> per region (fill-rule evenodd, holes are inner rings)
with data-n, its colour number counted from 1, light to dark, and
data-label "x y r", where its number goes (the middle of its widest
part) and how far that is from its edge. With --ink the picture's own
black outlines (a print's or a drawing's lines) are kept as paths with
data-ink, drawn on top, not painted. The root carries data-palette,
data-count (of regions), data-sig (a fingerprint of the regions, so
progress is not carried over to a picture made differently), data-mode
("big", "ink" or "ink2") and, from --set, what haltia-paint shows: data-name,
data-theme, data-level.

The steps follow drake7707/paintbynumbersgenerator (MIT), with what the
bench (bench/) showed brings it nearer Happy Color:
- brighten the old varnish, shrink, smooth keeping the edges (a guided
  filter, so brushwork does not make speckled regions), reduce to a few
  colours (k-means in Lab, where distance is close to how different they
  look);
- connected areas of one colour are regions; regions too small to tap
  or too thin for a number (--big-numbers: thin for one read without
  zooming far in) go to the neighbour with a long shared border, a
  colour alike and a weak edge between, until at most so many are left
  as the level allows; neighbours of one colour join in every round;
- borders are traced once between each pair of regions, on the corners
  of the pixels, so neighbours share them exactly; then smoothed and
  simplified, so that two regions never leave a gap between them.
All the heavy work is numpy and scipy: on the tablet a 300-region
picture takes some 15 s, a 600-region one some 20 s.
"""
import argparse
import gzip
import hashlib
import os
import time
from xml.sax.saxutils import quoteattr

import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps
from scipy import ndimage
from scipy.cluster.vq import kmeans2, vq

# Long side of the region map in pixels; SVG coordinates are in these.
SIDE = 1000
# Levels: at most so many regions, of at most so many colours; speckles
# below the detail size (pixels) join what surrounds them.
LEVELS = {2: (120, 14, 5), 3: (300, 18, 5), 4: (600, 24, 3), 5: (1000, 28, 3)}
# The thinnest a region may be (picture units): its number has to fit.
# With big numbers it can be read without zooming far in, for fewer
# regions (about a quarter fewer).
MIN_RADIUS, MIN_RADIUS_BIG = 2.5, 3.5
# A small region this unlike (Lab ΔE) the neighbour it would join is a
# detail that stays (an eye, a highlight), if no thinner than this
# (picture units).
DETAIL_DE, DETAIL_RADIUS = 18, 2.0
# The colour of a picture's own outlines (--ink).
INK = (34, 30, 28)
# How much of the picture's darkness counts as its outlines, by --ink
# level: a line has to lie on a ground lighter than this (Lab lightness).
# 1 (мало, --ink): clear lines only; 2 (много, --more-ink): lines on
# darker grounds too.
INK_GROUND = {1: 50, 2: 40}


# sRGB 0..255 to linear light, as a table: the power for each pixel is
# slow on the tablet.
_LINEAR = np.array([c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                    for c in np.arange(256) / 255.0], np.float32)


def lab(rgb):
    """sRGB (n, 3) bytes to CIE Lab, where distance is close to how
    different two colours look."""
    xyz = _LINEAR[rgb] @ (np.array([[0.4124, 0.2126, 0.0193],
                                    [0.3576, 0.7152, 0.1192],
                                    [0.1805, 0.0722, 0.9505]], np.float32)
                          / np.array([0.9505, 1.0, 1.089], np.float32))
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack((116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]),
                     200 * (f[:, 1] - f[:, 2])), -1)


def shrink(img, side, crop=None):
    """The picture (cut to crop, fractions x0 y0 x1 y1, if given) without
    its even margin, a little brighter, shrunk to side along its long
    edge: an (h, w, 3) byte array."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    if crop:
        w, h = img.size
        img = img.crop((round(crop[0] * w), round(crop[1] * h),
                        round(crop[2] * w), round(crop[3] * h)))
    # Large photos: decoded smaller to begin with (JPEG draft), then cut
    # down before the slower steps.
    if max(img.size) > 3 * side:
        img.thumbnail((3 * side, 3 * side), Image.BILINEAR)
    # An even margin (the paper round a drawing) is not part of it.
    corner = Image.new("RGB", img.size, img.getpixel((0, 0)))
    box = ImageChops.difference(img, corner).convert("L").point(lambda v: v > 24 and 255).getbbox()
    if box and (box[2] - box[0]) * (box[3] - box[1]) > 0.3 * img.size[0] * img.size[1]:
        img = img.crop(box)
    # Old varnish makes paintings brown and dull; a little brighter and
    # more saturated, more makes skies violet.
    img = ImageOps.autocontrast(img, cutoff=0.5, preserve_tone=True)
    img = ImageEnhance.Color(img).enhance(1.2)
    w, h = img.size
    if w >= h:
        size = side, max(8, round(side * h / w))
    else:
        size = max(8, round(side * w / h)), side
    return np.asarray(img.resize(size, Image.LANCZOS).filter(ImageFilter.MedianFilter(3)))


def guided(rgb, radius=3, eps=0.0025):
    """Flat where the picture varies little, its edges kept: a guided
    filter of each channel by itself (He et al.), box filters only, its
    coefficients worked out at half the size (the "fast guided filter":
    a quarter of the work, on the tablet some 2 s less). The brush strokes
    and grain that would make speckled regions go."""
    h, w, _ = rgb.shape
    out = np.empty(rgb.shape, np.float32)
    size = radius  # about the box of 2 radius + 1 at half the size
    for c in range(3):
        i = rgb[:, :, c].astype(np.float32) / 255
        half = i[::2, ::2]
        mean = ndimage.uniform_filter(half, size)
        var = ndimage.uniform_filter(half * half, size) - mean * mean
        a = var / (var + eps)
        b = mean - a * mean
        a = ndimage.uniform_filter(a, size).repeat(2, 0).repeat(2, 1)[:h, :w]
        b = ndimage.uniform_filter(b, size).repeat(2, 0).repeat(2, 1)[:h, :w]
        out[:, :, c] = a * i + b
    return (out.clip(0, 1) * 255 + 0.5).astype(np.uint8)


def lightness(rgb):
    """CIE L* (0 to 100) of each pixel, from luminance alone."""
    y = _LINEAR[rgb] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    return np.where(y > 0.008856, 116 * np.cbrt(y) - 16, 903.3 * y)


def edges(light):
    """How strong an edge the picture has at each pixel, 0 to 1, from its
    lightness."""
    light = ndimage.gaussian_filter(light, 1)
    g = np.hypot(ndimage.sobel(light, 0), ndimage.sobel(light, 1))
    return (g / (np.percentile(g, 99) + 1e-6)).clip(0, 1)


def ink_lines(light, width=7, contrast=12, dark=45, least=20, ground=50):
    """The picture's own outlines, as on a print or a drawing: lines
    darker than what is round them by contrast (Lab lightness), darker
    than dark, on a ground lighter than ground (dark textures, such as
    water, leaves or feathers, are dark round about too) and thinner than
    width pixels (a black-hat). Fainter stretches (half the contrast, a
    little lighter) count where they carry on such a line, so lines do not
    break up; whatever is broader than a line, with what is round it, is
    not one; specks under least pixels are dropped. (Before this, whole
    dark parts of some prints went black.) light: lightness()."""
    closed = ndimage.grey_closing(light, size=width)
    hat = closed - light
    on_light = closed > ground
    strong = (hat > contrast) & (light < dark) & on_light
    lines = (hat > contrast / 2) & (light < dark + 15) & on_light
    lines = ndimage.binary_closing(lines | strong, np.ones((3, 3), bool))
    broad = ndimage.distance_transform_edt(lines) > width / 2
    lines &= ndimage.distance_transform_edt(~broad) > width // 2 + 1
    parts, n = ndimage.label(lines, np.ones((3, 3), bool))
    if not n:
        return lines
    has_strong = np.bincount(parts[strong & lines], minlength=n + 1) > 0
    size = np.bincount(parts.ravel(), minlength=n + 1)
    keep = has_strong & (size >= least)
    keep[0] = False
    return keep[parts]


def reduce(rgb, colours, detail=5):
    """The small picture reduced to at most colours: (index array,
    palette as a list of (r, g, b)). Speckles smaller than detail pixels
    join what surrounds them."""
    h, w, _ = rgb.shape
    flat = rgb.reshape(-1, 3)
    pixels = lab(flat)
    # k-means in Lab on a sample, a few more centres than wanted.
    rng = np.random.default_rng(1)
    sample = pixels[rng.choice(len(pixels), min(len(pixels), 20000), replace=False)]
    centres, _ = kmeans2(sample, colours + 6, minit="++", seed=rng, iter=20)
    idx, _ = vq(pixels, centres)
    counts = np.bincount(idx, minlength=len(centres))
    # Most used first; a colour hard to tell from one already kept goes
    # to that one.
    keep, to = [], np.zeros(len(centres), np.int64)
    for i in np.argsort(-counts):
        if not counts[i]:
            continue
        near = [k for k, j in enumerate(keep) if np.linalg.norm(centres[i] - centres[j]) < 9]
        if near or len(keep) == colours:
            d = [np.linalg.norm(centres[i] - centres[j]) for j in keep]
            to[i] = int(np.argmin(d))
        else:
            to[i] = len(keep)
            keep.append(i)
    idx = to[idx]
    img_idx = Image.fromarray(idx.reshape(h, w).astype(np.uint8), "L")
    if detail > 1:
        img_idx = img_idx.filter(ImageFilter.ModeFilter(detail))
    return np.asarray(img_idx).astype(np.int32), len(keep)


def mean_colours(idx, rgb, n):
    """Each colour as the average of the pixels it stands for."""
    flat = idx.ravel()
    total = np.bincount(flat, minlength=n).clip(1)
    mean = np.stack([np.bincount(flat, rgb.reshape(-1, 3)[:, k].astype(float), n) / total
                     for k in range(3)], 1)
    return [tuple(int(round(v)) for v in c) for c in mean]


def components(idx, colours):
    """Connected areas of one colour: (labels, colour of each label)."""
    labels = np.zeros(idx.shape, np.int32)
    colour_of = []
    for c in range(colours):
        lab, n = ndimage.label(idx == c)
        if n:
            mask = lab > 0
            labels[mask] = lab[mask] + len(colour_of) - 1
            colour_of.extend([c] * n)
    return labels, np.array(colour_of, np.int32)


def inner_distance(labels):
    """Distance of each pixel to the nearest pixel of another region or
    the picture's edge."""
    edge = np.zeros(labels.shape, bool)
    edge[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    edge[:, :-1] |= labels[:, 1:] != labels[:, :-1]
    edge[1:, :] |= labels[1:, :] != labels[:-1, :]
    edge[:-1, :] |= labels[1:, :] != labels[:-1, :]
    edge[0, :] = edge[-1, :] = True
    edge[:, 0] = edge[:, -1] = True
    return ndimage.distance_transform_edt(~edge)


def border_pairs(labels, strength):
    """Every pair of 4-neighbour pixels in different regions: (a, b, the
    edge strength there)."""
    a = np.concatenate((labels[:, :-1].ravel(), labels[:-1, :].ravel()))
    b = np.concatenate((labels[:, 1:].ravel(), labels[1:, :].ravel()))
    g = np.concatenate((np.maximum(strength[:, :-1], strength[:, 1:]).ravel(),
                        np.maximum(strength[:-1, :], strength[1:, :]).ravel()))
    diff = a != b
    return a[diff], b[diff], g[diff]


def best_neighbours(a, b, g, n, small, colour_lab, is_ink):
    """For each small region the neighbour to join, -1 for none: a long
    shared border, a colour alike, a weak edge between them (so a detail
    of its own colour is not swallowed by whatever is largest round it).
    An outline takes a region only when nothing else is near."""
    src, dst, g = np.concatenate((a, b)), np.concatenate((b, a)), np.concatenate((g, g))
    want = small[src]
    keys, inv, counts = np.unique(src[want].astype(np.int64) * n + dst[want],
                                  return_inverse=True, return_counts=True)
    src, dst = keys // n, keys % n
    edge = np.bincount(inv, g[want], len(keys)) / counts
    alike = np.exp(-np.linalg.norm(colour_lab[src] - colour_lab[dst], axis=1) / 12)
    score = counts * alike * (1 - 0.8 * edge)
    score[is_ink[dst]] *= 0.02
    # Per source the best: sort by source, then score descending.
    order = np.lexsort((-score, src))
    src, dst = src[order], dst[order]
    first = np.ones(len(src), bool)
    first[1:] = src[1:] != src[:-1]
    best = np.full(n, -1, np.int64)
    best[src[first]] = dst[first]
    return best


def roots(parent):
    """Pointer jumping until each points at the end of its chain."""
    for _ in range(64):
        nxt = parent[parent]
        if (nxt == parent).all():
            break
        parent = nxt
    return parent


def radii(labels, dist, n):
    """Each region's largest distance from its edge."""
    out = np.zeros(n)
    np.maximum.at(out, labels.ravel(), dist.ravel())
    return out


def merge(labels, colour_of, colour_lab, strength, regions, min_area, min_radius, ink=None):
    """Give small and thin regions to their neighbours until at most
    regions are left and each has min_area and min_radius; neighbours that
    end up one colour become one region in every round, so the count aimed
    at is the count reached. Area is cheap to count, so thinness is
    measured only once the sizes are right. A detail is kept: a small
    region whose best neighbour is still far from its colour (an eye's
    pupil next to its pink rim, a highlight), down to a third of
    min_area and DETAIL_RADIUS; its number is small, but what the picture
    shows stays; only the count of regions takes it away. Regions of
    colour ink (the picture's own outlines) stay, take what is too small
    between them, and do not count."""
    thin_rounds = 0
    while True:
        n = len(colour_of)
        is_ink = colour_of == ink
        area = np.bincount(labels.ravel(), minlength=n)
        real = n - int(is_ink.sum())
        a, b, g = border_pairs(labels, strength)
        lab_of = colour_lab[colour_of]

        def joining(small, keep_details):
            """The small regions that go, and where (their best neighbour)."""
            best = best_neighbours(a, b, g, n, small, lab_of, is_ink)
            go = small & (best >= 0)
            far = np.linalg.norm(lab_of - lab_of[np.maximum(best, 0)], axis=1) > DETAIL_DE
            return go & ~(far & keep_details), best

        small = (area < min_area) & ~is_ink
        keep = area >= min_area / 3
        if real > regions:
            # The least ones above the limit as well, details or not: small
            # and like what is round them (the average colour along their
            # border) go first, so a pupil outlasts a patch of fur; a few
            # at a time so that the rest are measured again after.
            pairs = np.bincount(a, minlength=n) + np.bincount(b, minlength=n)
            round_ = np.stack([np.bincount(a, lab_of[b, k], n) + np.bincount(b, lab_of[a, k], n)
                               for k in range(3)], 1) / np.maximum(pairs, 1)[:, None]
            stands_out = np.linalg.norm(lab_of - round_, axis=1)
            worth = area * (1 + stands_out / DETAIL_DE) ** 2
            order = np.argsort(np.where(is_ink, np.inf, worth))
            over = np.zeros(n, bool)
            over[order[:max(1, (real - regions) // 4)]] = True
            small |= over
            keep &= ~over
        go, best = joining(small, keep) if small.any() else (small, None)
        if not go.any():
            radius = radii(labels, inner_distance(labels), n)
            small = (radius < min_radius) & ~is_ink
            if not small.any() or thin_rounds == 4:
                return labels, colour_of
            thin_rounds += 1
            go, best = joining(small, keep & (radius >= DETAIL_RADIUS))
            if not go.any():
                return labels, colour_of
        # Each small region points to its best neighbour; chains and
        # pairs pointing at each other end in the larger region.
        parent = np.arange(n)
        parent[go] = best[go]
        ids = np.arange(n)
        for _ in range(64):
            nxt = parent[parent]
            # A pair pointing at each other: the larger keeps itself.
            loop = (nxt == ids) & (parent != ids)
            loop &= (area > area[parent]) | ((area == area[parent]) & (ids > parent))
            parent[loop] = ids[loop]
            nxt = parent[parent]
            if (nxt == parent).all():
                break
            parent = nxt
        # Neighbours now of one colour become one region.
        a, b = parent[a], parent[b]
        same = (a != b) & (colour_of[a] == colour_of[b])
        a, b = a[same], b[same]
        for _ in range(64):
            if not len(a):
                break
            low = np.minimum(parent[a], parent[b])
            np.minimum.at(parent, parent[a], low)
            np.minimum.at(parent, parent[b], low)
            parent = roots(parent)
            if (parent[a] == parent[b]).all():
                break
        kept, new = np.unique(parent, return_inverse=True)
        labels = new[labels].astype(np.int32)
        colour_of = colour_of[kept]


def label_points(labels, n):
    """Where each region's number goes: among its widest pixels (at
    least nine tenths of its largest distance from its edge) the one
    nearest its middle, so a long region has it in the middle and not at
    one end. (rows, columns, radius) per region."""
    h, w = labels.shape
    dist = inner_distance(labels)
    radius = radii(labels, dist, n)
    flat = labels.ravel()
    top = np.flatnonzero(dist.ravel() >= radius[flat] * 0.9)
    ys, xs = np.divmod(top, w)
    area = np.bincount(flat, minlength=n).clip(1)
    all_y, all_x = np.divmod(np.arange(h * w), w)
    cy = np.bincount(flat, all_y, n) / area
    cx = np.bincount(flat, all_x, n) / area
    of = flat[top]
    far = (ys - cy[of]) ** 2 + (xs - cx[of]) ** 2
    order = np.lexsort((far, of))
    first = np.ones(len(order), bool)
    first[1:] = of[order][1:] != of[order][:-1]
    pick = top[order[first]]
    rows, cols = np.divmod(pick, w)
    return rows, cols, dist.ravel()[pick]


def trace(labels):
    """The borders between regions as chains of pixel corners, each
    between two junctions (or a closed loop): [(xs, ys, left, right)],
    left and right the regions on either hand walking along it, -1 for
    outside the picture."""
    h, w = labels.shape
    p = np.full((h + 2, w + 2), -1, np.int32)
    p[1:-1, 1:-1] = labels
    # hseg[y, x]: from corner (x, y) to (x + 1, y); vseg: (x, y) to (x, y + 1).
    hseg = p[0:h + 1, 1:w + 1] != p[1:h + 2, 1:w + 1]
    vseg = p[1:h + 1, 0:w + 1] != p[1:h + 1, 1:w + 2]
    # Directions 0..3 are right, down, left, up; bit 1 << d is set at a
    # corner when a border leaves it that way.
    bits = np.zeros((h + 1, w + 1), np.uint8)
    bits[:, :w] |= hseg * np.uint8(1)
    bits[:h, :] |= vseg * np.uint8(2)
    bits[:, 1:] |= hseg * np.uint8(4)
    bits[1:, :] |= vseg * np.uint8(8)
    w1 = w + 1
    move = (1, w1, -1, -w1)
    opposite = (2, 3, 0, 1)
    # The one direction of a single bit.
    direction = [0] * 16
    for d in range(4):
        direction[1 << d] = d
    degree = np.zeros(bits.shape, np.uint8)
    for d in range(4):
        degree += (bits >> d) & 1
    flat = bits.ravel().tolist()
    node = (degree.ravel() > 2).tolist()
    pix = p.ravel().tolist()
    pw = w + 2
    # used[c * 4 + d]: the border leaving corner c in direction d is done.
    used = bytearray(len(flat) * 4)

    def sides(c, d):
        x, y = c % w1, c // w1
        # p is padded by one: pixel (x, y) is p[y + 1][x + 1].
        at = (y + 1) * pw + x + 1
        if d == 0:
            return pix[at - pw], pix[at]
        if d == 1:
            return pix[at], pix[at - 1]
        if d == 2:
            return pix[at - 1], pix[at - pw - 1]
        return pix[at - pw - 1], pix[at - pw]

    chains = []

    def walk(start, d):
        left, right = sides(start, d)
        pts = [start]
        c = start
        while True:
            used[c * 4 + d] = 1
            c += move[d]
            back = opposite[d]
            used[c * 4 + back] = 1
            pts.append(c)
            if c == start or node[c]:
                break
            d = direction[flat[c] & ~(1 << back)]
        arr = np.array(pts)
        chains.append((arr % w1, arr // w1, left, right))

    for c in np.flatnonzero(degree.ravel() > 2).tolist():
        for d in range(4):
            if flat[c] >> d & 1 and not used[c * 4 + d]:
                walk(c, d)
    # What is left are closed loops: islands without a junction.
    for c in np.flatnonzero(degree.ravel() == 2).tolist():
        for d in (0, 1):
            if flat[c] >> d & 1 and not used[c * 4 + d]:
                walk(c, d)
    return chains


def smooth(xs, ys, closed, rounds=5):
    """Round off the pixel steps: a [1 2 1] average a few times; the ends
    of an open chain stay where they are, on the junctions."""
    pts = np.stack((xs, ys), 1).astype(float)
    if len(pts) < 3:
        return pts
    for _ in range(rounds):
        if closed:
            ring = pts[:-1]
            ring = (np.roll(ring, 1, 0) + 2 * ring + np.roll(ring, -1, 0)) / 4
            pts = np.vstack((ring, ring[:1]))
        else:
            pts[1:-1] = (pts[:-2] + 2 * pts[1:-1] + pts[2:]) / 4
    return pts


def simplify(pts, tolerance):
    """Drop points closer than tolerance to the line between their
    neighbours; every other point per pass, so that two neighbours are
    never dropped at once. The ends stay."""
    for parity in (1, 0, 1, 0, 1, 0):
        if len(pts) < 4:
            break
        a, b, c = pts[:-2], pts[1:-1], pts[2:]
        ac = c - a
        norm = np.hypot(ac[:, 0], ac[:, 1])
        cross = np.abs(ac[:, 0] * (b[:, 1] - a[:, 1]) - ac[:, 1] * (b[:, 0] - a[:, 0]))
        drop = cross < tolerance * np.maximum(norm, 1e-9)
        drop[parity::2] = False
        keep = np.ones(len(pts), bool)
        keep[1:-1] = ~drop
        pts = pts[keep]
    return pts


def rings(chains, n):
    """Each region's outline as closed rings of points."""
    ends = [{} for _ in range(n)]
    out = [[] for _ in range(n)]
    for i, (pts, left, right) in enumerate(chains):
        closed = len(pts) > 2 and (pts[0] == pts[-1]).all()
        for region, rev in ((left, False), (right, True)):
            if region < 0:
                continue
            if closed:
                out[region].append(pts)
            else:
                start = tuple(pts[-1] if rev else pts[0])
                ends[region].setdefault(start, []).append((i, rev))
    for region in range(n):
        todo = ends[region]
        while todo:
            start = next(iter(todo))
            ring = []
            at = start
            while at in todo:
                i, rev = todo[at].pop()
                if not todo[at]:
                    del todo[at]
                pts = chains[i][0][::-1] if rev else chains[i][0]
                ring.append(pts if not ring else pts[1:])
                at = tuple(pts[-1])
                if at == start:
                    break
            out[region].append(np.vstack(ring))
    return out


def picture(img, regions=300, colours=18, side=SIDE, detail=5, crop=None,
            min_area=None, min_radius=MIN_RADIUS, tolerance=0.25, ink=False, timing=None,
            progress=None, raster=False):
    """The region picture of a PIL image as a dict: w, h, palette,
    regions [(colour number from 0, label (x, y, r), rings)] and ink
    [rings] (the picture's own outlines, kept black, when ink: 1 or 2,
    INK_GROUND). progress,
    if given, is called with how much is done (0 to 1) after each step.
    raster: also the pixels it was made from, for the bench and tests:
    "raster" (rgb, labels, colour of each label, colours, ink colour or
    None, and per label its number's row, column and radius)."""
    t = [time.monotonic()]

    def lap(name):
        t.append(time.monotonic())
        if timing is not None:
            timing.append((name, t[-1] - t[-2]))
        if progress is not None:
            progress(DONE_AFTER[name.split()[0]])

    rgb = shrink(img, side, crop)
    light = lightness(rgb)
    lines = ink_lines(light, ground=INK_GROUND[int(ink)]) if ink else None
    if lines is not None:
        # The colours come from round the lines, not from the lines.
        _d, (iy, ix) = ndimage.distance_transform_edt(lines, return_indices=True)
        rgb_fill = rgb[iy, ix]
    else:
        rgb_fill = rgb
    lap("shrink")
    idx, count = reduce(guided(rgb_fill), colours, detail)
    keep = mean_colours(idx, rgb_fill, count)
    ink_colour = None
    if lines is not None:
        ink_colour = count
        idx = np.where(lines, count, idx)
        keep.append(INK)
    lap("reduce")
    labels, colour_of = components(idx, len(keep))
    lap("components %d" % len(colour_of))
    h, w = labels.shape
    if min_area is None:
        min_area = w * h / regions / 30
    colour_lab = lab(np.array(keep, np.uint8))
    labels, colour_of = merge(labels, colour_of, colour_lab, edges(light), regions,
                              min_area, min_radius, ink_colour)
    lap("merge %d" % len(colour_of))
    n = len(colour_of)
    rows, cols, radius = label_points(labels, n)
    lap("labels")
    chains = []
    for xs, ys, left, right in trace(labels):
        closed = len(xs) > 2 and xs[0] == xs[-1] and ys[0] == ys[-1]
        chains.append((simplify(smooth(xs, ys, closed), tolerance), left, right))
    lap("trace %d" % len(chains))
    outlines = rings(chains, n)
    lap("rings")
    # Colours that are left, numbered light to dark (the outlines' black
    # is not a colour to paint).
    present = sorted(set(colour_of.tolist()) - {ink_colour},
                     key=lambda i: -(0.299 * keep[i][0] + 0.587 * keep[i][1] + 0.114 * keep[i][2]))
    number = {c: k for k, c in enumerate(present)}
    extra = {"raster": (rgb, labels, colour_of, keep, ink_colour, rows, cols, radius)} if raster else {}
    return {**extra, "w": w, "h": h,
            "palette": ["#%02x%02x%02x" % keep[c] for c in present],
            "regions": [(number[int(colour_of[r])],
                         (cols[r] + 0.5, rows[r] + 0.5, float(radius[r])),
                         outlines[r]) for r in range(n) if colour_of[r] != ink_colour],
            "ink": [outlines[r] for r in range(n) if colour_of[r] == ink_colour]}


def to_svg(pic, meta=None):
    """The picture as SVG text; meta becomes data- attributes of the root.
    data-sig is a fingerprint of the regions, so a picture made again
    differently does not take the progress of the old one."""
    def path(outline):
        # Pairs after M are line-tos in SVG, so no L is needed.
        return "".join("M" + " ".join("%.1f %.1f" % (px, py) for px, py in ring[:-1]) + "Z"
                       for ring in outline)

    body = ['<path d="%s" fill="%s" data-n="%d" data-label="%.1f %.1f %.1f"/>'
            % (path(outline), pic["palette"][n], n + 1, x, y, r)
            for n, (x, y, r), outline in pic["regions"]]
    sig = hashlib.sha1("\n".join(body).encode()).hexdigest()[:12]
    # The picture's own outlines, black, on top of the regions; not
    # painted, not counted.
    if pic.get("ink"):
        body.append('<path d="%s" fill="#%02x%02x%02x" data-ink="1"/>'
                    % (("".join(path(outline) for outline in pic["ink"]),) + INK))
    extra = "".join(" data-%s=%s" % (k, quoteattr(str(v))) for k, v in (meta or {}).items())
    head = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
            'data-palette="%s" data-count="%d" data-sig="%s" fill-rule="evenodd"%s>'
            % (pic["w"], pic["h"], pic["w"], pic["h"], " ".join(pic["palette"]),
               len(pic["regions"]), sig, extra))
    return "\n".join([head] + body + ["</svg>\n"])


# How much of the work is done after each step of picture(), roughly as
# the steps take on the tablet (merging is most of it).
DONE_AFTER = {"shrink": 0.05, "reduce": 0.15, "components": 0.2, "merge": 0.65,
              "labels": 0.75, "trace": 0.9, "rings": 0.95}


def write(pic, path, meta=None):
    """Write the picture as gzipped SVG, replacing path only when done."""
    with gzip.open(path + ".new", "wb", compresslevel=9) as fh:
        fh.write(to_svg(pic, meta).encode())
    os.replace(path + ".new", path)


def mode_name(big, ink):
    """data-mode: "big" for big numbers, "ink" or "ink2" for outlines."""
    return " ".join(m for m, on in (("big", big), ("ink" if ink == 1 else "ink%d" % ink, ink))
                    if on)


def main():
    args = argparse.ArgumentParser(description="A picture as paint by number regions.")
    args.add_argument("image")
    args.add_argument("out", help="the .svgz to write")
    args.add_argument("--level", type=int, choices=sorted(LEVELS), default=3)
    args.add_argument("--side", type=int, default=SIDE)
    args.add_argument("--crop", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"),
                      help="the part of the image to use, as fractions")
    args.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                      help="a data- attribute of the picture, such as name=...")
    args.add_argument("-v", "--verbose", action="store_true")
    args.add_argument("--progress", action="store_true",
                      help='print "progress F" lines, F the share done')
    args.add_argument("--big-numbers", action="store_true",
                      help="no region too thin for a number read without zooming far in")
    args.add_argument("--ink", action="store_true",
                      help="keep the picture's own black outlines (prints, drawings), clear ones")
    args.add_argument("--more-ink", action="store_true",
                      help="as --ink, with lines on darker grounds too")
    opts = args.parse_args()
    regions, colours, detail = LEVELS[opts.level]
    ink = 2 if opts.more_ink else 1 if opts.ink else 0
    timing = []
    start = time.monotonic()

    def progress(done):
        print("progress %.2f" % done, flush=True)

    pic = picture(Image.open(opts.image), regions, colours, opts.side, detail, opts.crop,
                  min_radius=MIN_RADIUS_BIG if opts.big_numbers else MIN_RADIUS,
                  ink=ink, timing=timing, progress=progress if opts.progress else None)
    meta = {"mode": mode_name(opts.big_numbers, ink)}
    meta.update(kv.split("=", 1) for kv in opts.set)
    write(pic, opts.out, {k: v for k, v in meta.items() if v})
    if opts.progress:
        progress(1)
    if opts.verbose:
        for name, sec in timing:
            print("%-20s %6.2f s" % (name, sec))
        print("total %.2f s, %d regions, %d colours"
              % (time.monotonic() - start, len(pic["regions"]), len(pic["palette"])))


if __name__ == "__main__":
    main()
