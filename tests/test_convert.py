# SPDX-License-Identifier: GPL-2.0
"""Преобразование (haltia_paint.convert) with a stand-in for pbn.py."""
import os
import queue
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from haltia_paint.convert import CANCELLED, DONE, Conversion  # noqa: E402

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_pbn.py")


class ConversionTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.log = os.path.join(self.dir, "log")
        os.environ["FAKE_PBN_LOG"] = self.log
        self.events = queue.Queue()
        self.conversion = Conversion(FAKE, notify=lambda fn: fn(), timeout=20)

    def tearDown(self):
        self.conversion.stop()
        shutil.rmtree(self.dir)

    def source(self, name, what):
        path = os.path.join(self.dir, name + ".src")
        with open(path, "w") as fh:
            fh.write(what)
        return path

    def submit(self, name, what, urgent=False):
        return self.conversion.submit(
            self.source(name, what), os.path.join(self.dir, name), 3, {"name": name},
            urgent=urgent,
            on_progress=lambda job, share: self.events.put(("progress", name, share)),
            on_done=lambda job, ok: self.events.put(("done", name, ok)))

    def done(self, count):
        """The next count "done" events, as {name: ok}."""
        result = {}
        while len(result) < count:
            kind, name, value = self.events.get(timeout=15)
            if kind == "done":
                result[name] = value
        return result

    def runs(self):
        with open(self.log) as fh:
            return fh.read().split("\n")[:-1]

    def test_writes_the_picture_and_tells_progress(self):
        job = self.submit("a", "ok")
        events = [self.events.get(timeout=15) for _ in range(3)]
        self.assertEqual(events, [("progress", "a", 0.25), ("progress", "a", 1.0),
                                  ("done", "a", True)])
        self.assertEqual(job.state, DONE)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "a")))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "a.new")))

    def test_one_at_a_time(self):
        self.submit("a", "sleep 0.3")
        self.submit("b", "sleep 0.3")
        self.submit("c", "ok")
        self.assertEqual(self.done(3), {"a": True, "b": True, "c": True})
        self.assertEqual(self.runs(), ["start a", "end a", "start b", "end b",
                                       "start c", "end c"])

    def test_failure_leaves_nothing(self):
        self.submit("a", "fail")
        self.assertEqual(self.done(1), {"a": False})
        self.assertEqual(sorted(os.listdir(self.dir)), ["a.src", "log"])

    def test_cancel_waiting(self):
        self.submit("a", "sleep 0.5")
        b = self.submit("b", "ok")
        b.cancel()
        self.submit("c", "ok")
        self.assertEqual(self.done(2), {"a": True, "c": True})
        self.assertEqual(b.state, CANCELLED)
        self.assertNotIn("start b", self.runs())

    def test_cancel_running_stops_it(self):
        a = self.submit("a", "sleep 10")
        while "start a" not in (self.runs() if os.path.exists(self.log) else []):
            self.events.get(timeout=5)
        a.cancel()
        self.submit("b", "ok")
        self.assertEqual(self.done(1), {"b": True})
        self.assertEqual(a.state, CANCELLED)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "a.new")))
        self.assertNotIn("end a", self.runs())

    def test_urgent_stops_background_which_starts_again(self):
        self.submit("photo", "sleep 1")
        while not os.path.exists(self.log):
            self.events.get(timeout=5)
        self.submit("preview", "ok", urgent=True)
        done = []
        while len(done) < 2:
            kind, name, _value = self.events.get(timeout=15)
            if kind == "done":
                done.append(name)
        self.assertEqual(done, ["preview", "photo"])
        self.assertEqual(self.runs(), ["start photo", "start preview", "end preview",
                                       "start photo", "end photo"])

    def test_urgent_goes_first_in_the_queue(self):
        self.submit("a", "sleep 0.3", urgent=True)
        self.submit("b", "ok")
        self.submit("c", "ok", urgent=True)
        self.done(3)
        self.assertEqual([r for r in self.runs() if r.startswith("start")],
                         ["start a", "start c", "start b"])

    def test_bytes_are_written_and_removed(self):
        self.conversion.submit(b"ok", os.path.join(self.dir, "a"), 3,
                               on_done=lambda job, ok: self.events.put(("done", "a", ok)))
        self.assertEqual(self.done(1), {"a": True})
        self.assertFalse(os.path.exists(os.path.join(self.dir, "a.img")))

    def test_timeout_fails(self):
        self.conversion.timeout = 0.3
        self.submit("a", "sleep 5")
        self.assertEqual(self.done(1), {"a": False})

    def test_stop_cancels_all(self):
        a = self.submit("a", "sleep 5")
        b = self.submit("b", "ok")
        self.conversion.stop()
        self.assertEqual((a.state, b.state), (CANCELLED, CANCELLED))


if __name__ == "__main__":
    unittest.main()
