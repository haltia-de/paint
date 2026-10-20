# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`haltia-paint` is a colour-by-number game on public-domain paintings in the style
of Happy Color / Daily Coloring (numbered irregular regions), made for an
older player on a Lenovo YOGA Tablet 10 (B8000-H) running the
Haltia shell ([haltia-de/device-lenovo-b8000h](https://github.com/haltia-de/device-lenovo-b8000h)).
Big cells and buttons, no timer, score or ads. The UI and README are in
Russian; code, comments, docstrings and commit messages are in English
(British spelling: "colour").

It was split out of lenovo-b8000h-linux; the shell's image build installs it
from here by tag. Since v3.0 it is a standalone desktop program (ADR 0001 in
lenovo-b8000h-linux: device / shell / programs): GApplication id
`io.github.haltia_de.Paint` (also `GLib.set_prgname` before GTK loads, the
Wayland app id), no `b8k_ui`, dialogs from `haltia_kit.dialogs`; it meets the
shell only through `data/<id>.desktop` (`X-B8K-Home`, `X-B8K-Replaces`).
Since 4.0 (ADR 0004, repo haltia-de/paint) the package is `haltia-paint`
(`provides`/`replaces` b8k-paint); until 5.0 the old names stay: the
`b8k-paint` command is a link, `data/io.github.trudenboy.Paint.desktop` is a
hidden entry, and `main()` moves `~/.local/share/b8k-paint` to `haltia-paint`
(`haltia_kit.paths.migrate_dirs`).
The shell buzzes touches and its GTK theme sizes the header and dialogs. Don't
edit the lenovo repo; tell its session the new tag.

## Running and installing

Tests: `python3 -m unittest discover -s tests` (stdlib only, no GTK or
numpy; the APKBUILD's `check()` runs them); `uvx pyflakes haltia-paint
pbn.py make-paintings.py haltia_paint tests` is a quick check. Requirements: Python 3, GTK 3,
PyGObject, pycairo, Pillow; `pbn.py` also needs numpy and scipy (Alpine:
`apk add python3 py3-gobject3 gtk+3.0 py3-cairo py3-pillow py3-numpy py3-scipy`); exact tested versions for a
Flatpak in `requirements.txt`). No path is built from `~` (`expanduser`): in a Flatpak the home folder
is there but unreadable, so folders come from `GLib.get_user_*_dir()` and
`get_user_special_dir()`. Nothing may hard-code `/usr`: everything
is found from the program's own place (a Flatpak has `/app`). Own pictures come only
from XDG Pictures (photos to make into pictures in `Pictures/Раскраски`, moved
from `~/Раскраски` by `move_photos()` with their ids) and `Gtk.FileChooserNative`
(no walking `/media`).

```
PYTHONPATH=../b8k-compat ./haltia-paint   # run from the checkout (pictures/ and pbn.py beside it)
./haltia-paint --open ID       # go straight to one picture (e.g. builtin-fox, wd-Q123-4)
sh install.sh [ROOT] [PREFIX]  # PREFIX /usr/local by default, /usr in the APKBUILD
python3 make-paintings.py CACHE_DIR [SLUG...]  # regenerate pictures/*.svgz from Wikimedia Commons
python3 pbn.py -v --level 3 IMAGE OUT.svgz     # one picture; levels 3/4/5 = ~300/600/1000 regions
```

`BUILTIN`, `PBN` and the `haltia_paint` package are found beside the program
in a checkout (`pictures/`, `pbn.py`, `haltia_paint/`), else under the install
prefix (`PREFIX/share/haltia-paint/`, `PREFIX/lib/haltia-paint/pbn.py` and
`.../haltia_paint/`).

The tablet (Lenovo B8000-H) is armv7, 1 GB RAM: `pbn.py` takes ~15 s for 300
regions and ~20 s for 600 there, a full-screen redraw ~0.75 s. Commons
answers 429 when downloading many files; `make-paintings.py` retries.

## Layout

- `haltia-paint` — the program (no `.py` extension): GTK pages, board,
  gallery. Module docstring describes the behaviour in detail; keep it in
  sync. What needs no screen moves into the `haltia_paint/` package, one
  deep module at a time, each tested in `tests/` (see `CONTEXT.md` for the
  names):
  - `haltia_paint/convert.py` — Преобразование: the one queue of `pbn.py`
    runs (one process at a time, urgent before background, background
    stopped and started again for urgent work, cancel, timeout, progress
    from `pbn.py --progress`). `tests/fake_pbn.py` stands in for pbn.py.
- `pbn.py` — the region generator (raster to paint-by-number SVG), used by
  `make-paintings.py` as a module and by the program as a subprocess.
- `make-paintings.py` — offline generator for `pictures/*.svgz`. `PAINTINGS`
  lists slug, Commons file name, Russian title, theme, level.
- `pictures/*.svgz` — built-in pictures, gzipped SVG: one `<path>` per
  region (`fill-rule` evenodd, holes as inner rings, `M x y x y ...Z`) with
  `data-n` (colour number from 1, light to dark) and `data-label` "x y r"
  (where the number goes, inradius); root carries `data-palette`,
  `data-count`, `data-name`, `data-theme`, `data-level`, `data-source`.
- `data/` — `.desktop`, hicolor SVG icon, AppStream metainfo.
- Packages: `packaging/alpine/APKBUILD`; `debian/` (deps from noble and
  trixie plus our `python3-haltia-kit`; the pre-4.0 names are left out);
  `packaging/flatpak/io.github.haltia_de.Paint.yml` (GNOME 51, its
  Python 3.14; `haltia-kit.yml` is a copy of haltia-de/kit's module;
  numpy, scipy, Pillow as cp314 manylinux wheels per arch, keep them at
  `requirements.txt`; pycairo from the runtime; `--filesystem=xdg-pictures`).
  Build the Flatpak from the checkout with
  `flatpak run org.flatpak.Builder --user --install --force-clean build <manifest>`.

## Architecture notes

- **Levels** are numeric codes in the SVG and gallery sections (`SECTIONS` in
  `haltia-paint`); 2 = ~120 regions (some built-ins); 3/4/5 = at most 300/600/1000 regions with 18/24/28
  colours (`LEVELS` in `pbn.py`, `GRADES` in `haltia-paint` must agree);
  built-ins use 3 and 4, 5 only for downloads; 8 = downloaded from
  Wikidata; 9 = user photos.
- **Generator** (`pbn.py`, after drake7707/paintbynumbersgenerator): Lab
  k-means colours, mode filter, connected components, merging small/thin
  regions into the neighbour with the longest shared border (area first,
  thinness by distance transform only when sizes are right), then borders
  traced once per region pair on pixel corners so neighbours share them
  exactly, smoothed and simplified. Coordinates: 1000 units on the long side.
- **Rendering** (`Board`): the board pans and zooms itself (a
  ScrolledWindow cost a third of the frames); it is drawn in `TILE` px
  tiles, in a thread of its own, cached until the zoom changes. A tap
  paints its region into the tiles kept; the chosen colour's highlight is
  part of the tiles, so changing colour repaints the regions of the old
  and new colour in the tiles in view. Hit test: a `GRID` of region
  boxes, then `cairo.in_fill`; a miss falls back to the nearest unpainted
  region of the chosen colour within `FINGER` px via `in_stroke`.
- **Picture ids** prefix the source: `builtin-<slug>`, `photo-<hash>`,
  `wd-<QID>-<level>`. Progress lives in
  `~/.local/share/haltia-paint/progress/<id>.json` as `{"count", "filled": [region
  indexes]}`; a count mismatch resets it. `last` stores the last opened id.
- **Photos and downloads** are converted through `Conversion`
  (`haltia_paint/convert.py`): `pbn.py` in a niced subprocess, one at a
  time (1 GB of RAM); a preview is urgent and stops a photo, which starts
  again after it; leaving the preview cancels its sizes. Photos cache to
  `~/.local/share/haltia-paint/photos/` (a photo that failed gets
  `<key>.failed` and is tried again only from its «Ещё раз» button),
  search previews to `.../work/`.
- Regions are parsed lazily (`regions_of`); gallery thumbnails render on
  first draw and are cached as PNG; progress is written shortly after the
  last tap.
- **Network** (search, "+ Найти"): only https to wikidata.org,
  commons.wikimedia.org and the Wikimedia image hosts (`IMAGE_HOSTS`), with
  `AGENT` as User-Agent. Work runs in background threads / `Workers` (a
  few threads; concurrent.futures took a third of a second to import);
  results return to GTK via `GLib.idle_add`, with a
  generation counter (`search_gen`) to drop stale results.

## Conventions

- Commit messages: `haltia-paint: <short sentence>.` style (`b8k-paint:` before 4.0).
- Files carry `SPDX-License-Identifier: GPL-2.0`; LF line endings
  (`.gitattributes`).
- Every `<release>` in the metainfo carries a short `<description>` saying
  what the person will notice: since 4.1.3 in English with a Russian
  `xml:lang="ru"` twin (before, Russian only); haltia-update shows it as
  «Что нового» before installing. `debian/changelog` gets each version too
  (CI checks it equals the tag).
- Inside the Haltia shell (`ON_HALTIA`, from `XDG_CURRENT_DESKTOP`) the
  header has no close button, the shell's ✕ covers it; elsewhere it shows
  the desktop's buttons.
