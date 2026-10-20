# SPDX-License-Identifier: GPL-2.0
"""A stand-in for pbn.py in the tests: same command line; what it does is
written in the source image file: "ok", "fail", or "sleep SECONDS".
Each run appends "start OUT" and "end OUT" to the file in $FAKE_PBN_LOG."""
import os
import sys
import time


def main():
    # --progress --level N SOURCE OUT [--set KEY=VALUE ...], as Conversion runs it
    source, out = sys.argv[4:6]
    log = os.environ["FAKE_PBN_LOG"]
    with open(log, "a") as fh:
        fh.write("start %s\n" % os.path.basename(out))
    with open(source) as fh:
        what = fh.read().split()
    print("progress 0.25", flush=True)
    with open(out + ".new", "w") as fh:
        fh.write("half")
    if what[0] == "sleep":
        time.sleep(float(what[1]))
    if what[0] == "fail":
        sys.stderr.write("it went wrong\n")
        sys.exit(1)
    os.replace(out + ".new", out)
    print("progress 1.00", flush=True)
    with open(log, "a") as fh:
        fh.write("end %s\n" % os.path.basename(out))


if __name__ == "__main__":
    main()
