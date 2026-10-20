#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Install haltia-paint (Раскраска): sh install.sh [ROOT] [PREFIX]
# ROOT empty or / for this system; PREFIX /usr/local unless given (a
# package passes /usr). It needs Python 3 with PyGObject (GTK 3) and
# haltia-kit (github.com/haltia-de/kit), pycairo and Pillow, and for
# photos and found paintings numpy and scipy. The .desktop file shows it
# in any desktop's launcher; the Haltia tablet shell puts it on its home
# screen (X-B8K-Home).
set -eu
root=${1:-}
root=${root%/}
prefix=${2:-/usr/local}
here=$(cd "$(dirname "$0")" && pwd)
share=$root$prefix/share
id=io.github.haltia_de.Paint
old=io.github.trudenboy.Paint
install -D -m 755 "$here/haltia-paint" "$root$prefix/bin/haltia-paint"
install -D -m 644 "$here/data/$id.desktop" "$share/applications/$id.desktop"
install -D -m 644 "$here/data/$id.svg" "$share/icons/hicolor/scalable/apps/$id.svg"
install -D -m 644 "$here/data/$id.metainfo.xml" "$share/metainfo/$id.metainfo.xml"
# The names before 4.0 (ADR 0004): the command and the .desktop file
# (hidden, for what still calls the old id) stay until 5.0.
ln -sf haltia-paint "$root$prefix/bin/b8k-paint"
install -D -m 644 "$here/data/$old.desktop" "$share/applications/$old.desktop"
rm -f "$share/icons/hicolor/scalable/apps/$old.svg" "$share/metainfo/$old.metainfo.xml"
rm -rf "$root$prefix/lib/b8k-paint" "$share/b8k-paint"
# The shell's old entry for this program, from before the .desktop file.
rm -f "$root/usr/local/share/b8k/apps.d/paint.conf" "$root/usr/local/share/b8k/paint.svg"
# The generator, for photos and found paintings.
install -D -m 644 "$here/pbn.py" "$root$prefix/lib/haltia-paint/pbn.py"
# The program's own modules (haltia_paint/), beside the generator.
rm -rf "$root$prefix/lib/haltia-paint/haltia_paint"
install -d -m 755 "$root$prefix/lib/haltia-paint/haltia_paint"
install -m 644 "$here"/haltia_paint/*.py "$root$prefix/lib/haltia-paint/haltia_paint/"
# The built-in pictures (make-paintings.py makes them); where version 2
# kept them, they go.
rm -rf "$share/haltia-paint" "$root/usr/local/share/b8k/paint"
install -d -m 755 "$share/haltia-paint"
install -m 644 "$here"/pictures/*.svgz "$share/haltia-paint/"
# The paintings they were made from (for «Оригинал»), and the sounds.
install -d -m 755 "$share/haltia-paint/originals" "$share/haltia-paint/sounds"
install -m 644 "$here"/pictures/originals/*.jpg "$share/haltia-paint/originals/"
install -m 644 "$here"/data/sounds/*.oga "$share/haltia-paint/sounds/"
# Version 2 went into /usr/local; from a package it would come first in
# PATH and stay the one that runs.
if [ "$prefix" != /usr/local ]; then
	rm -rf "$root/usr/local/bin/b8k-paint" "$root/usr/local/lib/b8k-paint"
fi
