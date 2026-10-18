# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`b8k-paint` is a colour-by-number game on public-domain paintings in the style
of Happy Color / Daily Coloring (numbered irregular regions), made for an
older player on a Lenovo YOGA Tablet 10 (B8000-H) running the
[lenovo-b8000h-linux](https://github.com/trudenboy/lenovo-b8000h-linux) shell.
Big cells and buttons, no timer, score or ads. The UI and README are in
Russian; code, comments, docstrings and commit messages are in English
(British spelling: "colour").

It was split out of lenovo-b8000h-linux; the shell's image build installs it
from here by tag. Since v3.0 it is a standalone desktop program (ADR 0001 in
lenovo-b8000h-linux: device / shell / programs): GApplication id
`io.github.trudenboy.Paint` (also `GLib.set_prgname` before GTK loads, the
Wayland app id), no `b8k_ui`, dialogs from `b8k_compat.dialogs`; it meets the
shell only through `data/<id>.desktop` (`X-B8K-Home`, `X-B8K-Replaces=paint`).
The shell buzzes touches and its GTK theme sizes the header and dialogs. Don't
edit the lenovo repo; tell its session the new tag.

## Running and installing

There is no build or test suite (`uvx pyflakes b8k-paint pbn.py
make-paintings.py` is a quick check). Requirements: Python 3, GTK 3,
PyGObject, pycairo, Pillow; `pbn.py` also needs numpy and scipy (Alpine:
`apk add python3 py3-gobject3 gtk+3.0 py3-cairo py3-pillow py3-numpy py3-scipy`).

```
PYTHONPATH=../b8k-compat ./b8k-paint   # run from the checkout (pictures/ and pbn.py beside it)
./b8k-paint --open ID       # go straight to one picture (e.g. builtin-fox, wd-Q123-4)
sh install.sh [ROOT] [PREFIX]  # PREFIX /usr/local by default, /usr in the APKBUILD
python3 make-paintings.py CACHE_DIR [SLUG...]  # regenerate pictures/*.svgz from Wikimedia Commons
python3 pbn.py -v --level 3 IMAGE OUT.svgz     # one picture; levels 3/4/5 = ~300/600/1000 regions
```

`BUILTIN` and `PBN` are found beside the program in a checkout
(`pictures/`, `pbn.py`), else under the install prefix
(`PREFIX/share/b8k-paint/`, `PREFIX/lib/b8k-paint/pbn.py`).

The tablet (Lenovo B8000-H) is armv7, 1 GB RAM: `pbn.py` takes ~15 s for 300
regions and ~20 s for 600 there, a full-screen redraw ~0.75 s. Commons
answers 429 when downloading many files; `make-paintings.py` retries.

## Layout

- `b8k-paint` — the whole program, one Python file (no `.py` extension).
  Module docstring describes the behaviour in detail; keep it in sync.
- `pbn.py` — the region generator (raster to paint-by-number SVG), used by
  `make-paintings.py` as a module and by the program as a subprocess.
- `make-paintings.py` — offline generator for `pictures/*.svgz`. `PAINTINGS`
  lists slug, Commons file name, Russian title, theme, level.
- `pictures/*.svgz` — built-in pictures, gzipped SVG: one `<path>` per
  region (`fill-rule` evenodd, holes as inner rings, `M x y x y ...Z`) with
  `data-n` (colour number from 1, light to dark) and `data-label` "x y r"
  (where the number goes, inradius); root carries `data-palette`,
  `data-count`, `data-name`, `data-theme`, `data-level`, `data-source`.
- `data/` — `.desktop`, hicolor SVG icon, AppStream metainfo;
  `packaging/alpine/APKBUILD`.

## Architecture notes

- **Levels** are numeric codes in the SVG and gallery sections (`LEVELS` in
  `b8k-paint`); 3/4/5 = at most 300/600/1000 regions with 18/24/28
  colours (`LEVELS` in `pbn.py`, `GRADES` in `b8k-paint` must agree);
  built-ins use 3 and 4, 5 only for downloads; 8 = downloaded from
  Wikidata; 9 = user photos.
- **Generator** (`pbn.py`, after drake7707/paintbynumbersgenerator): Lab
  k-means colours, mode filter, connected components, merging small/thin
  regions into the neighbour with the longest shared border (area first,
  thinness by distance transform only when sizes are right), then borders
  traced once per region pair on pixel corners so neighbours share them
  exactly, smoothed and simplified. Coordinates: 1000 units on the long side.
- **Rendering** (`Board`): the board is a DrawingArea of `scale * size`
  inside a ScrolledWindow; it is drawn in `TILE` px tiles cached until the
  zoom changes. A tap invalidates only the tiles under the region's box;
  the chosen colour's blue highlight is drawn over the tiles on every
  draw, so changing colour costs no tiles. Hit test: a `GRID` of region
  boxes, then `cairo.in_fill`; a miss falls back to the nearest unpainted
  region of the chosen colour within `FINGER` px via `in_stroke`.
- **Picture ids** prefix the source: `builtin-<slug>`, `photo-<hash>`,
  `wd-<QID>-<level>`. Progress lives in
  `~/.local/share/b8k-paint/progress/<id>.json` as `{"count", "filled": [region
  indexes]}`; a count mismatch resets it. `last` stores the last opened id.
- **Photos and downloads** are converted by running `pbn.py` in a niced
  subprocess (keeps the GTK thread and the GIL free); photos cache to
  `~/.local/share/b8k-paint/photos/`, search previews to `.../work/`.
- Regions are parsed lazily (`regions_of`); gallery thumbnails render on
  first draw and are cached as PNG; progress is written shortly after the
  last tap.
- **Network** (search, "+ Найти"): only https to wikidata.org,
  commons.wikimedia.org and the Wikimedia image hosts (`IMAGE_HOSTS`), with
  `AGENT` as User-Agent. Work runs in background threads / a
  `ThreadPoolExecutor`; results return to GTK via `GLib.idle_add`, with a
  generation counter (`search_gen`) to drop stale results.

## Conventions

- Commit messages: `b8k-paint: <short sentence>.` style, as in the history.
- Files carry `SPDX-License-Identifier: GPL-2.0`; LF line endings
  (`.gitattributes`).
