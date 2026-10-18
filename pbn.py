#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Paint by number in regions: a picture split into numbered areas.

  pbn.py [--level 3|4|5] [--set name=...] IMAGE OUT.svgz

A painting becomes a map of regions, one colour number each, written as
SVG: one <path> per region (fill-rule evenodd, holes are inner rings)
with data-n, its colour number counted from 1, light to dark, and
data-label "x y r", the point furthest from its edge and that distance,
where its number goes. The root carries data-palette, data-count (of
regions) and, from --set,
what b8k-paint shows: data-name, data-theme, data-level.

The steps follow drake7707/paintbynumbersgenerator (MIT):
- brighten the old varnish, shrink, smooth, reduce to a few colours
  (k-means in Lab, where distance is close to how different they look);
- connected areas of one colour are regions; regions too small to tap
  or too thin for a number go to the neighbour they share the longest
  border with, until at most so many are left as the level allows;
- borders are traced once between each pair of regions, on the corners
  of the pixels, so neighbours share them exactly; then smoothed and
  simplified, so that two regions never leave a gap between them.
All the heavy work is numpy and scipy: on the tablet a 300-region
picture takes some 15 s, a 600-region one some 20 s.
"""
import argparse
import gzip
import os
import time
from xml.sax.saxutils import quoteattr

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from scipy import ndimage
from scipy.cluster.vq import kmeans2, vq

# Long side of the region map in pixels; SVG coordinates are in these.
SIDE = 1000
# Levels: at most so many regions, of at most so many colours; speckles
# below the detail size (pixels) join what surrounds them.
LEVELS = {3: (300, 18, 5), 4: (600, 24, 3), 5: (1000, 28, 3)}


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


def reduce(img, side, colours, detail=5):
    """The picture shrunk to side along its long edge and reduced to at
    most colours: (index array, palette as a list of (r, g, b)). Speckles
    smaller than detail pixels join what surrounds them."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    # Old varnish makes paintings brown and dull; a little brighter and
    # more saturated, more makes skies violet.
    img = ImageOps.autocontrast(img, cutoff=0.5, preserve_tone=True)
    img = ImageEnhance.Color(img).enhance(1.2)
    w, h = img.size
    if w >= h:
        size = side, max(8, round(side * h / w))
    else:
        size = max(8, round(side * w / h)), side
    small = img.resize(size, Image.LANCZOS).filter(ImageFilter.MedianFilter(3))
    rgb = np.asarray(small).reshape(-1, 3)
    pixels = lab(rgb)
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
    img_idx = Image.fromarray(idx.reshape(size[1], size[0]).astype(np.uint8), "L")
    if detail > 1:
        img_idx = img_idx.filter(ImageFilter.ModeFilter(detail))
    idx = np.asarray(img_idx).astype(np.int32)
    # Each colour is the average of the pixels it stands for.
    flat = idx.ravel()
    n = len(keep)
    total = np.bincount(flat, minlength=n).clip(1)
    mean = np.stack([np.bincount(flat, rgb[:, k].astype(float), n) / total for k in range(3)], 1)
    return idx, [tuple(int(round(v)) for v in c) for c in mean]


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


def best_neighbours(labels, n, small):
    """For each small region the neighbour it shares the longest border
    with, -1 for none."""
    a = np.concatenate((labels[:, :-1].ravel(), labels[:-1, :].ravel()))
    b = np.concatenate((labels[:, 1:].ravel(), labels[1:, :].ravel()))
    diff = a != b
    a, b = a[diff], b[diff]
    src, dst = np.concatenate((a, b)), np.concatenate((b, a))
    want = small[src]
    keys, counts = np.unique(src[want].astype(np.int64) * n + dst[want], return_counts=True)
    src, dst = keys // n, keys % n
    # Per source the longest border: sort by source, then count descending.
    order = np.lexsort((-counts, src))
    src, dst = src[order], dst[order]
    first = np.ones(len(src), bool)
    first[1:] = src[1:] != src[:-1]
    best = np.full(n, -1, np.int64)
    best[src[first]] = dst[first]
    return best


def radii(labels, dist, n):
    """Each region's largest distance from its edge."""
    out = np.zeros(n)
    np.maximum.at(out, labels.ravel(), dist.ravel())
    return out


def merge(labels, colour_of, regions, min_area, min_radius):
    """Give small and thin regions to their neighbours until at most
    regions are left and each has min_area and min_radius. Area is cheap
    to count, so thinness is measured only once the sizes are right."""
    thin_rounds = 0
    while True:
        n = len(colour_of)
        area = np.bincount(labels.ravel(), minlength=n)
        small = area < min_area
        if n > regions:
            # The smallest ones above the limit as well; a few at a time
            # so that the rest are measured again after.
            small[np.argsort(area)[:max(1, (n - regions) // 4)]] = True
        if not small.any():
            small = radii(labels, inner_distance(labels), n) < min_radius
            if not small.any() or thin_rounds == 4:
                # Neighbours that ended up the same colour become one region.
                return components(colour_of[labels], colour_of.max() + 1)
            thin_rounds += 1
        best = best_neighbours(labels, n, small)
        # Each small region points to its best neighbour; chains and
        # pairs pointing at each other end in the larger region.
        parent = np.arange(n)
        go = small & (best >= 0)
        parent[go] = best[go]
        for _ in range(64):
            nxt = parent[parent]
            # A pair pointing at each other: the larger keeps itself.
            loop = (nxt == np.arange(n)) & (parent != np.arange(n))
            ids = np.arange(n)
            loop &= (area > area[parent]) | ((area == area[parent]) & (ids > parent))
            parent[loop] = np.arange(n)[loop]
            nxt = parent[parent]
            if (nxt == parent).all():
                break
            parent = nxt
        roots, new = np.unique(parent, return_inverse=True)
        labels = new[labels].astype(np.int32)
        colour_of = colour_of[roots]


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


def picture(img, regions=300, colours=18, side=SIDE, detail=5, min_area=None, min_radius=2.5,
            tolerance=0.25, timing=None):
    """The region picture of a PIL image as a dict: w, h, palette, and
    regions [(colour number from 0, label (x, y, r), rings)]."""
    t = [time.monotonic()]

    def lap(name):
        t.append(time.monotonic())
        if timing is not None:
            timing.append((name, t[-1] - t[-2]))

    idx, keep = reduce(img, side, colours, detail)
    lap("reduce")
    labels, colour_of = components(idx, len(keep))
    lap("components %d" % len(colour_of))
    h, w = labels.shape
    if min_area is None:
        min_area = w * h / regions / 30
    labels, colour_of = merge(labels, colour_of, regions, min_area, min_radius)
    lap("merge %d" % len(colour_of))
    dist = inner_distance(labels)
    n = len(colour_of)
    radius = radii(labels, dist, n)
    # Where each region is widest: the first pixel at its largest distance.
    top = np.flatnonzero(dist.ravel() == radius[labels.ravel()])
    _, first = np.unique(labels.ravel()[top], return_index=True)
    where = [divmod(int(i), w) for i in top[first]]
    lap("labels")
    chains = []
    for xs, ys, left, right in trace(labels):
        closed = len(xs) > 2 and xs[0] == xs[-1] and ys[0] == ys[-1]
        chains.append((simplify(smooth(xs, ys, closed), tolerance), left, right))
    lap("trace %d" % len(chains))
    outlines = rings(chains, n)
    lap("rings")
    # Colours that are left, numbered light to dark.
    present = sorted(set(colour_of.tolist()),
                     key=lambda i: -(0.299 * keep[i][0] + 0.587 * keep[i][1] + 0.114 * keep[i][2]))
    number = {c: k for k, c in enumerate(present)}
    return {"w": w, "h": h,
            "palette": ["#%02x%02x%02x" % keep[c] for c in present],
            "regions": [(number[int(colour_of[r])],
                         (where[r][1] + 0.5, where[r][0] + 0.5, float(radius[r])),
                         outlines[r]) for r in range(n)]}


def to_svg(pic, meta=None):
    """The picture as SVG text; meta becomes data- attributes of the root."""
    extra = "".join(" data-%s=%s" % (k, quoteattr(str(v))) for k, v in (meta or {}).items())
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
           'data-palette="%s" data-count="%d" fill-rule="evenodd"%s>'
           % (pic["w"], pic["h"], pic["w"], pic["h"], " ".join(pic["palette"]),
              len(pic["regions"]), extra)]
    for n, (x, y, r), outline in pic["regions"]:
        # Pairs after M are line-tos in SVG, so no L is needed.
        d = ["M" + " ".join("%.1f %.1f" % (px, py) for px, py in ring[:-1]) + "Z"
             for ring in outline]
        out.append('<path d="%s" fill="%s" data-n="%d" data-label="%.1f %.1f %.1f"/>'
                   % ("".join(d), pic["palette"][n], n + 1, x, y, r))
    out.append("</svg>\n")
    return "\n".join(out)


def write(pic, path, meta=None):
    """Write the picture as gzipped SVG, replacing path only when done."""
    with gzip.open(path + ".new", "wb", compresslevel=9) as fh:
        fh.write(to_svg(pic, meta).encode())
    os.replace(path + ".new", path)


def main():
    args = argparse.ArgumentParser(description="A picture as paint by number regions.")
    args.add_argument("image")
    args.add_argument("out", help="the .svgz to write")
    args.add_argument("--level", type=int, choices=sorted(LEVELS), default=3)
    args.add_argument("--side", type=int, default=SIDE)
    args.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                      help="a data- attribute of the picture, such as name=...")
    args.add_argument("-v", "--verbose", action="store_true")
    opts = args.parse_args()
    regions, colours, detail = LEVELS[opts.level]
    timing = []
    start = time.monotonic()
    pic = picture(Image.open(opts.image), regions, colours, opts.side, detail, timing=timing)
    write(pic, opts.out, dict(kv.split("=", 1) for kv in opts.set))
    if opts.verbose:
        for name, sec in timing:
            print("%-20s %6.2f s" % (name, sec))
        print("total %.2f s, %d regions, %d colours"
              % (time.monotonic() - start, len(pic["regions"]), len(pic["palette"])))


if __name__ == "__main__":
    main()
