# SPDX-License-Identifier: GPL-2.0
"""Отклик: a sound and a buzz when a colour or the whole picture is done,
a quiet sound, no buzz, for a tap on a region of another colour, and the
short buzz of every other tap.

    feedback = Feedback(sounds_folder, app_id, sound=True, vibration=True,
                        miss=True)
    feedback.colour_done()
    feedback.picture_done()
    feedback.missed()   # a tap on a region of another colour
    feedback.tapped()   # a button
    feedback.hit()      # a region painted

The sound is one of the program's own files (colour.oga, picture.oga,
miss.oga), played by paplay in a process of its own: the tablet runs PulseAudio and
has paplay but not GStreamer's PulseAudio output, a desktop's PipeWire
takes paplay too, and nothing is loaded into the program. Without paplay
it stays silent.

The buzz is the Haltia shell's own, haltia-press (the motor itself, 70 ms
a pulse, as the panel's buttons buzz): one pulse for a tap, two for a
colour, three for a picture. feedbackd took the events on the tablet but
its motor never moved (4.7.2), so it is only what is tried without
haltia-press: an event over D-Bus with the "quiet" profile, so it only
vibrates. Without either nothing buzzes.

The tap buzz: the Haltia shell buzzes every tap itself, unless the
program in front says it answers touches itself (X-Haltia-Own-Feedback
in its .desktop file, haltia-shell 2.8); then the shell keeps
$XDG_RUNTIME_DIR/haltia/quiet-taps while it is in front, and only then
does tapped() buzz, as long as the shell's own (touchguard's buzz_ms)
is not 0. So a miss is not felt, and with an older shell, or none, taps
are buzzed once, by the shell or not at all. Each is tried and
forgotten: nothing here waits or fails.
"""
import os
import shutil
import subprocess
import sys

# feedbackd events (the Event naming spec) and how they buzz in its
# default theme: a short buzz for a colour, a long one for a picture.
COLOUR_EVENT = "message-new-instant"  # 150 ms
PICTURE_EVENT = "message-new-email"  # 750 ms
TAP_EVENT = "bell-terminal"  # 100 ms, near the shell's 70
# Which taps on the picture buzz (Настройки): a right one, a miss, both
# or none.
TAP_BUZZES = ("hit", "miss", "both", "none")
# The shell's buzz (a pulse of the motor), and pulses a gap apart for each
# event; feedbackd where the shell has no haltia-press.
PRESS = "/usr/libexec/haltia/haltia-press"
PULSES = {TAP_EVENT: 1, COLOUR_EVENT: 2, PICTURE_EVENT: 3}
GAP_MS = 180
# The shell's tap buzz: its length (0: none) in this file.
TOUCHGUARD = "/etc/haltia/touchguard.conf"


class Feedback:
    def __init__(self, sounds, app_id, sound=True, vibration=True, miss=True, player=None,
                 bus=None, quiet_taps=None, touchguard=TOUCHGUARD, taps="hit"):
        """sounds: the folder of the .oga files. player and bus
        stand in for paplay and the session bus in tests: player(argv),
        bus(app_id, event)."""
        self.sounds = sounds
        self.app_id = app_id
        self.sound = sound
        self.vibration = vibration
        self.miss = miss  # the sound of a miss, when there is sound at all
        self.player = player or self._play
        self.bus = bus or self._buzz
        self._paplay = None
        runtime = os.environ.get("XDG_RUNTIME_DIR", "")
        self.quiet_taps = quiet_taps or (os.path.join(runtime, "haltia", "quiet-taps")
                                         if runtime else "")
        self.tap_buzz = _buzz_ms(touchguard) != 0
        self.taps = taps if taps in TAP_BUZZES else "hit"

    def colour_done(self):
        self._give("colour.oga", COLOUR_EVENT)

    def picture_done(self):
        self._give("picture.oga", PICTURE_EVENT)

    def tapped(self):
        """A button tapped: buzzed here only while the shell leaves taps
        to the program."""
        if self.tap_buzz and self.quiet_taps and os.path.exists(self.quiet_taps):
            self.bus(self.app_id, TAP_EVENT)

    def hit(self):
        """A region painted: buzzed as a tap, when taps says so."""
        if self.taps in ("hit", "both"):
            self.tapped()

    def missed(self):
        if self.miss:
            self._give("miss.oga", None)
        if self.taps in ("miss", "both"):
            self.tapped()

    def _give(self, name, event):
        if self.sound:
            path = os.path.join(self.sounds, name)
            if os.path.exists(path):
                self.player(["paplay", path])
        if self.vibration and event:
            self.bus(self.app_id, event)

    def _play(self, argv):
        if self._paplay is None:
            self._paplay = shutil.which("paplay") or ""
        if not self._paplay:
            return
        try:
            subprocess.Popen([self._paplay] + argv[1:], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            sys.stderr.write("haltia-paint: paplay: %s\n" % exc)

    @staticmethod
    def _buzz(app_id, event):
        if os.access(PRESS, os.X_OK):
            from gi.repository import GLib

            def pulse():
                try:
                    # Its mark for a panel button of this name stays unused.
                    subprocess.Popen([PRESS, "paint"], stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except OSError as exc:
                    sys.stderr.write("haltia-paint: %s: %s\n" % (PRESS, exc))
                return False

            for k in range(PULSES.get(event, 1)):
                GLib.timeout_add(k * GAP_MS, pulse)
            return
        try:
            from gi.repository import Gio, GLib
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            # Not waited for: no answer is needed, and without feedbackd
            # the call just fails.
            bus.call("org.sigxcpu.Feedback", "/org/sigxcpu/Feedback", "org.sigxcpu.Feedback",
                     "TriggerFeedback",
                     GLib.Variant("(ssa{sv}i)", (app_id, event,
                                                 {"profile": GLib.Variant("s", "quiet")}, -1)),
                     None, Gio.DBusCallFlags.NO_AUTO_START, 2000, None, None)
        except Exception as exc:  # no bus at all
            sys.stderr.write("haltia-paint: feedback: %s\n" % exc)


def _buzz_ms(path):
    """touchguard's buzz_ms, or None when it does not say."""
    try:
        with open(path) as fh:
            for line in fh:
                key, _eq, value = line.partition("=")
                if key.strip() == "buzz_ms":
                    return int(value.split("#")[0].strip())
    except (OSError, ValueError):
        pass
    return None
