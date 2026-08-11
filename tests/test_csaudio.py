#!/usr/bin/env python3
"""Tests for scripts/csaudio.py — picking and feeding an audio player.

    python3 -m unittest discover tests

Nothing here plays a sound. `which` is stubbed so a machine's real players
cannot decide the outcome, which is also how the macOS path gets exercised
from Linux: afplay only plays files, so it needs the wav route rather than a
pipe, and that route has to be testable without a Mac.
"""

import os
import sys
import unittest
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import csaudio  # noqa: E402

RATE = 24000
PCM = b"\x00\x01" * 1200          # 1200 frames of s16le mono


class FakeWhich:
    """Stands in for shutil.which: only the named tools exist."""

    def __init__(self, *present):
        self.present = set(present)

    def __call__(self, name):
        return "/usr/bin/" + name if name in self.present else None


class PlayerSelection(unittest.TestCase):

    def setUp(self):
        self.real_which = csaudio.shutil.which

    def tearDown(self):
        csaudio.shutil.which = self.real_which

    def only(self, *tools):
        csaudio.shutil.which = FakeWhich(*tools)

    def test_pipewire_preferred(self):
        self.only("paplay", "aplay", "ffplay")
        self.assertEqual(csaudio.stream_cmd(RATE)[0], "paplay")

    def test_falls_down_the_list(self):
        for tools, want in [(("aplay", "ffplay"), "aplay"),
                            (("ffplay",), "ffplay"),
                            (("sox",), "play")]:      # sox installs as `play`
            with self.subTest(tools):
                self.only(*tools)
                self.assertEqual(csaudio.stream_cmd(RATE)[0], want)

    def test_rate_reaches_the_command(self):
        self.only("aplay")
        self.assertIn(str(RATE), csaudio.stream_cmd(RATE))

    def test_macos(self):
        # A stock Mac: afplay and nothing else. There is no pipe player, so
        # the caller has to take the file route.
        self.only("afplay")
        self.assertIsNone(csaudio.stream_cmd(RATE))
        self.assertEqual(csaudio.file_player(), "afplay")
        self.assertTrue(csaudio.available())

    def test_afplay_never_used_as_a_pipe(self):
        # It cannot read stdin. Treating it as a streaming player would look
        # like it worked and produce silence.
        self.only("afplay")
        self.assertIsNone(csaudio.stream_cmd(RATE))

    def test_ffplay_names_no_channel_count(self):
        # ffplay 7 removed -ac — the player exits with "Option not found",
        # the daemon reads the broken pipe as the reply being cancelled, and
        # the result is pure silence. Older ffplay lacks -ch_layout, the
        # replacement. The raw-pcm demuxer defaults to mono everywhere, so
        # the command must name no channel count at all.
        self.only("ffplay")
        cmd = csaudio.stream_cmd(RATE)
        self.assertNotIn("-ac", cmd)
        self.assertNotIn("-ch_layout", cmd)

    def test_bare_machine(self):
        self.only()
        self.assertIsNone(csaudio.stream_cmd(RATE))
        self.assertIsNone(csaudio.file_player())
        self.assertFalse(csaudio.available())

    def test_bare_machine_raises_rather_than_going_quiet(self):
        self.only()
        with self.assertRaises(RuntimeError):
            csaudio.play_blocking(PCM, RATE)


class WavContainer(unittest.TestCase):

    def test_header_matches_the_samples(self):
        path = csaudio.write_temp_wav(PCM, RATE)
        try:
            with wave.open(path) as w:
                self.assertEqual(w.getnchannels(), 1)
                self.assertEqual(w.getsampwidth(), 2)
                self.assertEqual(w.getframerate(), RATE)
                self.assertEqual(w.getnframes(), len(PCM) // 2)
                self.assertEqual(w.readframes(w.getnframes()), PCM)
        finally:
            os.unlink(path)

    def test_bytes_and_file_agree(self):
        path = csaudio.write_temp_wav(PCM, RATE)
        try:
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), csaudio.wav_bytes(PCM, RATE))
        finally:
            os.unlink(path)

    def test_temp_file_is_a_wav_on_disk(self):
        path = csaudio.write_temp_wav(PCM, RATE)
        try:
            self.assertTrue(path.endswith(".wav"))
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(4), b"RIFF")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
