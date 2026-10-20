#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""The program's two sounds, made here rather than taken from elsewhere:
colour.oga, a soft low chime when a colour is done (a higher one sounded
sharp), picture.oga, a short rising tune when a picture is done, and
miss.oga, a quiet low "тук" for a tap on a region of another colour.
Soft bells (a few partials dying away, a slow start), not loud: an older
player hears them in a quiet room.

    python3 data/sounds/make-sounds.py   # needs ffmpeg with libvorbis
"""
import math
import os
import struct
import subprocess
import tempfile
import wave

RATE = 44100


def bell(freq, length, loud, attack=0.005, bright=1.0, decay=4.0):
    """A bell-like note: the tone and two overtones (as loud as bright
    says), dying away; attack s to rise, softer when longer."""
    out = []
    for k in range(int(RATE * length)):
        t = k / RATE
        rise = min(1.0, t / attack)
        v = (math.sin(2 * math.pi * freq * t) * math.exp(-t * decay)
             + 0.4 * bright * math.sin(2 * math.pi * freq * 2.0 * t) * math.exp(-t * 7.0)
             + 0.15 * bright * math.sin(2 * math.pi * freq * 3.01 * t) * math.exp(-t * 11.0))
        out.append(loud * rise * v / 1.55)
    return out


def mix(parts, length):
    """Notes laid at their start times (s) into one track."""
    track = [0.0] * int(RATE * length)
    for start, note in parts:
        at = int(RATE * start)
        for k, v in enumerate(note[:len(track) - at]):
            track[at + k] += v
    # A short fade at the end, so it does not click.
    fade = int(RATE * 0.05)
    for k in range(fade):
        track[-1 - k] *= k / fade
    return track


def write(path, track):
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "s.wav")
        with wave.open(raw, "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(RATE)
            fh.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v)) * 32000))
                                    for v in track))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-c:a", "libvorbis",
                        "-q:a", "3", "-map_metadata", "-1", "-f", "ogg", path], check=True)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    # G5 then C6, a slow start and few overtones: a calm "динь-дон".
    write(os.path.join(here, "colour.oga"),
          mix([(0, bell(783.99, 1.0, 0.22, attack=0.03, bright=0.3, decay=3.5)),
               (0.12, bell(1046.5, 1.0, 0.16, attack=0.03, bright=0.3, decay=3.5))], 1.1))
    # A low, short, dull note: "not this one", not a scolding.
    write(os.path.join(here, "miss.oga"),
          mix([(0, bell(196.0, 0.35, 0.30, attack=0.01, bright=0.15, decay=12.0))], 0.35))
    # C5 E5 G5, then C6 held.
    notes = [(0.0, 523.25), (0.16, 659.25), (0.32, 783.99), (0.48, 1046.5)]
    write(os.path.join(here, "picture.oga"),
          mix([(at, bell(f, 1.6 if f > 1000 else 0.6, 0.32)) for at, f in notes], 2.1))


if __name__ == "__main__":
    main()
