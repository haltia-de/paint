# SPDX-License-Identifier: GPL-2.0
"""Отклик: a sound and a buzz when a colour or the whole picture is done,
and a quiet sound, no buzz, for a tap on a region of another colour.

    feedback = Feedback(sounds_folder, app_id, sound=True, vibration=True,
                        miss=True)
    feedback.colour_done()
    feedback.picture_done()
    feedback.missed()

The sound is one of the program's own files (colour.oga, picture.oga,
miss.oga), played by paplay in a process of its own: the tablet runs PulseAudio and
has paplay but not GStreamer's PulseAudio output, a desktop's PipeWire
takes paplay too, and nothing is loaded into the program. Without paplay
it stays silent.

The buzz is an event of feedbackd (the tablet shell's), over D-Bus, with
the "quiet" profile so feedbackd only vibrates and plays no sound of its
own; feedbackd's own level (silent) still wins. Without feedbackd
nothing buzzes. Each is tried and forgotten: nothing here waits or fails.
"""
import os
import shutil
import subprocess
import sys

# feedbackd events (the Event naming spec) and how they buzz in its
# default theme: a short buzz for a colour, a long one for a picture.
COLOUR_EVENT = "message-new-instant"  # 150 ms
PICTURE_EVENT = "message-new-email"  # 750 ms


class Feedback:
    def __init__(self, sounds, app_id, sound=True, vibration=True, miss=True, player=None,
                 bus=None):
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

    def colour_done(self):
        self._give("colour.oga", COLOUR_EVENT)

    def picture_done(self):
        self._give("picture.oga", PICTURE_EVENT)

    def missed(self):
        if self.miss:
            self._give("miss.oga", None)

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
