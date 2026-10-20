# SPDX-License-Identifier: GPL-2.0
"""Преобразование: images made into pictures by pbn.py, one at a time.

The tablet has 1 GB and pbn.py takes a few hundred MB for some 15 s, so
only one runs, in a process of its own at low priority. Urgent work (a
preview the person is waiting for) goes first: it stops background work
(a photo of Раскраски), which starts again afterwards. A job cancelled
stops its process and leaves no file behind.

    conversion = Conversion(pbn_path, notify=GLib.idle_add)
    job = conversion.submit(source, out, level, {"name": ...}, urgent=True,
                            on_progress=..., on_done=...)
    job.cancel()
    conversion.stop()

on_progress(job, share) and on_done(job, ok) come through notify (on the
GTK thread in the program); a job cancelled gets neither again.
"""
import collections
import os
import subprocess
import sys
import tempfile
import threading

WAITING, RUNNING, DONE, CANCELLED = "waiting", "running", "done", "cancelled"


class Job:
    """One image to make into a picture; see Conversion.submit."""

    def __init__(self, conversion, source, out, level, meta, urgent, on_progress, on_done):
        self.conversion = conversion
        self.source = source
        self.out = out
        self.level = level
        self.meta = meta or {}
        self.urgent = urgent
        self.on_progress = on_progress
        self.on_done = on_done
        self.state = WAITING
        self.ok = None

    def cancel(self):
        """Never mind: taken off the queue, or its process stopped."""
        self.conversion.cancel(self)


class Conversion:
    """The one queue of pbn.py work; see the module's docstring."""

    def __init__(self, pbn, python=sys.executable, notify=None, timeout=600, nice=10):
        self.pbn = pbn
        self.python = python
        self.notify = notify or (lambda fn, *args: fn(*args))
        self.timeout = timeout
        self.nice = nice
        self.lock = threading.Condition()
        self.urgent = collections.deque()
        self.background = collections.deque()
        self.running = None
        self.process = None
        self.stopped = False
        # Why the running process was stopped: "cancel", "yield" (to
        # urgent work) or "timeout".
        self.why = None
        threading.Thread(target=self.work, daemon=True).start()

    def submit(self, source, out, level, meta=None, urgent=False,
               on_progress=None, on_done=None):
        """Make source (an image file's path, or its bytes) into the
        picture out at level (pbn.LEVELS), with meta as its data-
        attributes. Urgent work goes before background work, and stops
        background work that is running."""
        job = Job(self, source, out, level, meta, urgent, on_progress, on_done)
        with self.lock:
            (self.urgent if urgent else self.background).append(job)
            if urgent and self.running is not None and not self.running.urgent:
                self.halt("yield")
            self.lock.notify_all()
        return job

    def cancel(self, job):
        with self.lock:
            if job.state == WAITING:
                for line in (self.urgent, self.background):
                    if job in line:
                        line.remove(job)
            elif job.state == RUNNING:
                self.halt("cancel")
            else:
                return
            job.state = CANCELLED

    def stop(self):
        """Cancel everything and end the queue (the program is closing)."""
        with self.lock:
            self.stopped = True
            for job in list(self.urgent) + list(self.background):
                job.state = CANCELLED
            self.urgent.clear()
            self.background.clear()
            if self.running is not None:
                self.running.state = CANCELLED
                self.halt("cancel")
            self.lock.notify_all()

    def halt(self, why):
        """Stop the running process (with the lock held)."""
        self.why = self.why or why
        if self.process is not None:
            try:
                self.process.kill()
            except OSError:
                pass

    def work(self):
        while True:
            with self.lock:
                while not self.stopped and not self.urgent and not self.background:
                    self.lock.wait()
                if self.stopped:
                    return
                job = (self.urgent or self.background).popleft()
                job.state = RUNNING
                self.running, self.why = job, None
            ok = self.run(job)
            with self.lock:
                why, self.running, self.process = self.why, None, None
                if why == "yield" and job.state == RUNNING:
                    # Again from the start once the urgent work is done.
                    job.state = WAITING
                    self.background.appendleft(job)
                    continue
                if job.state != RUNNING:
                    continue  # cancelled
                job.state, job.ok = DONE, ok
            self.tell(job, job.on_done, ok)

    def run(self, job):
        """pbn.py for job, reading its progress; True when the picture is
        written."""
        source = job.source
        try:
            if isinstance(source, bytes):
                os.makedirs(os.path.dirname(job.out) or ".", exist_ok=True)
                with open(job.out + ".img", "wb") as fh:
                    fh.write(source)
                source = job.out + ".img"
            else:
                os.makedirs(os.path.dirname(job.out) or ".", exist_ok=True)
        except OSError as exc:
            sys.stderr.write("haltia-paint: %s: %s\n" % (job.out, exc))
            return False
        cmd = [self.python, self.pbn, "--progress", "--level", str(job.level), source, job.out]
        for key, value in job.meta.items():
            cmd += ["--set", "%s=%s" % (key, value)]
        log = tempfile.TemporaryFile()
        try:
            with self.lock:
                if job.state != RUNNING or self.why:
                    return False
                process = self.process = subprocess.Popen(
                    cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log)
            try:
                os.setpriority(os.PRIO_PROCESS, process.pid, self.nice)
            except OSError:
                pass
            timer = threading.Timer(self.timeout, self.timed_out, (process,))
            timer.daemon = True
            timer.start()
            for line in process.stdout:
                word = line.split()
                if job.on_progress and len(word) == 2 and word[0] == b"progress":
                    try:
                        share = float(word[1])
                    except ValueError:
                        continue
                    self.tell(job, job.on_progress, share)
            process.stdout.close()
            code = process.wait()
            timer.cancel()
            if code and not self.why:
                log.seek(0)
                sys.stderr.write("haltia-paint: %s: %s\n" % (
                    source, log.read().decode(errors="replace")[-500:]))
            elif self.why == "timeout":
                sys.stderr.write("haltia-paint: %s: took too long\n" % source)
            return code == 0 and not self.why
        except OSError as exc:
            sys.stderr.write("haltia-paint: %s: %s\n" % (source, exc))
            return False
        finally:
            log.close()
            for left in (job.out + ".new", job.out + ".img"):
                try:
                    os.remove(left)
                except OSError:
                    pass

    def tell(self, job, fn, value):
        """fn(job, value) through notify, unless the job is cancelled by
        the time it arrives."""
        if not fn:
            return

        def deliver():
            if job.state != CANCELLED:
                fn(job, value)
            return False  # once (GLib.idle_add)

        self.notify(deliver)

    def timed_out(self, process):
        with self.lock:
            if self.process is process:
                self.halt("timeout")
