#!/bin/sh
# SPDX-License-Identifier: GPL-2.0
# Install b8k-paint (Раскраска): sh install.sh [ROOT] [PREFIX]
# ROOT empty or / for this system; PREFIX /usr/local unless given (a
# package passes /usr). It needs Python 3 with PyGObject (GTK 3) and
# b8k-compat (github.com/trudenboy/b8k-compat), pycairo and Pillow, and
# for photos and found paintings numpy and scipy. The .desktop file
# shows it in any desktop's launcher; the b8k tablet shell puts it on its
# home screen (X-B8K-Home).
set -eu
root=${1:-}
root=${root%/}
prefix=${2:-/usr/local}
here=$(cd "$(dirname "$0")" && pwd)
share=$root$prefix/share
install -D -m 755 "$here/b8k-paint" "$root$prefix/bin/b8k-paint"
install -D -m 644 "$here/data/io.github.trudenboy.Paint.desktop" "$share/applications/io.github.trudenboy.Paint.desktop"
install -D -m 644 "$here/data/io.github.trudenboy.Paint.svg" "$share/icons/hicolor/scalable/apps/io.github.trudenboy.Paint.svg"
install -D -m 644 "$here/data/io.github.trudenboy.Paint.metainfo.xml" "$share/metainfo/io.github.trudenboy.Paint.metainfo.xml"
# The shell's old entry for this program, from before the .desktop file.
rm -f "$root/usr/local/share/b8k/apps.d/paint.conf" "$root/usr/local/share/b8k/paint.svg"
# The generator, for photos and found paintings.
install -D -m 644 "$here/pbn.py" "$root$prefix/lib/b8k-paint/pbn.py"
# The built-in pictures (make-paintings.py makes them); where version 2
# kept them, they go.
rm -rf "$share/b8k-paint" "$root/usr/local/share/b8k/paint"
install -d -m 755 "$share/b8k-paint"
install -m 644 "$here"/pictures/*.svgz "$share/b8k-paint/"
# Version 2 went into /usr/local; from a package it would come first in
# PATH and stay the one that runs.
if [ "$prefix" != /usr/local ]; then
	rm -rf "$root/usr/local/bin/b8k-paint" "$root/usr/local/lib/b8k-paint"
fi
