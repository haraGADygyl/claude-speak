#!/usr/bin/env python3
"""Play numbered voice samples one after another so you can pick one.

Each sample is synthesized and played synchronously, so voices never overlap
and no timers are involved.
"""

import os
import shutil
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cspaths  # noqa: E402

PICKS = [
    ("af_heart",   "American female, warm"),
    ("af_bella",   "American female, bright and expressive"),
    ("af_nicole",  "American female, soft and close-mic"),
    ("af_sarah",   "American female, neutral newsreader"),
    ("am_michael", "American male, calm and even"),
    ("am_puck",    "American male, lively"),
    ("am_fenrir",  "American male, deep"),
    ("bf_emma",    "British female, measured"),
    ("bm_george",  "British male, classic received pronunciation"),
    ("bm_fable",   "British male, storyteller"),
]

SAMPLE = ("I fixed the failing test in parser dot pi. The bug was an off by one "
          "error in the line counter, and all nineteen tests pass now.")

NUMBERS = ["one", "two", "three", "four", "five",
           "six", "seven", "eight", "nine", "ten"]


def play(samples, rate):
    if shutil.which("paplay"):
        cmd = ["paplay", "--raw", "--format=s16le",
               "--rate=%d" % rate, "--channels=1", "--client-name=ClaudeSpeak"]
    elif shutil.which("aplay"):
        cmd = ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(rate), "-c", "1"]
    elif shutil.which("ffplay"):
        cmd = ["ffplay", "-loglevel", "quiet", "-nodisp", "-autoexit",
               "-f", "s16le", "-ar", str(rate), "-ac", "1", "-"]
    else:
        print("no audio player found", file=sys.stderr)
        sys.exit(1)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    subprocess.run(cmd, input=pcm, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)      # blocks until played


def main():
    from kokoro_onnx import Kokoro

    kokoro = Kokoro(cspaths.MODEL, cspaths.VOICES)
    only = [a for a in sys.argv[1:] if a]
    picks = [p for p in PICKS if not only or p[0] in only]
    if not picks:
        picks = [(v, "requested voice") for v in only]

    for idx, (voice, desc) in enumerate(picks):
        label = "Voice %s. %s." % (
            NUMBERS[idx] if idx < len(NUMBERS) else str(idx + 1),
            voice.replace("_", " "))
        print("%2d. %-11s %s" % (idx + 1, voice, desc), flush=True)
        try:
            samples, rate = kokoro.create(label + " " + SAMPLE, voice=voice, speed=1.0)
        except Exception as exc:
            print("    (skipped: %s)" % exc, flush=True)
            continue
        play(samples, rate)


if __name__ == "__main__":
    main()
