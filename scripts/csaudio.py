#!/usr/bin/env python3
"""Getting PCM out of a speaker, on whatever the machine happens to have.

Two shapes, because macOS has neither of the usual players:

  streaming — paplay, aplay, ffplay, sox read raw PCM on stdin, so one
              process can play a whole reply as it is synthesized
  file      — afplay, which ships with macOS, only plays files. Each chunk
              becomes a short wav played to completion. Still chunk by
              chunk, just not down one long pipe

Standard library only, and no numpy: callers hand over bytes.
"""

import io
import os
import shutil
import subprocess
import tempfile
import wave


def stream_cmd(rate):
    """A player that accepts raw s16le mono on stdin, or None if there is none."""
    if shutil.which("paplay"):
        return ["paplay", "--raw", "--format=s16le",
                "--rate=%d" % rate, "--channels=1", "--client-name=ClaudeSpeak"]
    if shutil.which("aplay"):
        return ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(rate), "-c", "1"]
    if shutil.which("ffplay"):
        return ["ffplay", "-loglevel", "quiet", "-nodisp", "-autoexit",
                "-f", "s16le", "-ar", str(rate), "-ac", "1", "-"]
    if shutil.which("sox"):
        return ["play", "-q", "-t", "raw", "-r", str(rate), "-e", "signed",
                "-b", "16", "-c", "1", "-"]
    return None


def file_player():
    """A player that takes a path instead of a pipe, or None."""
    return "afplay" if shutil.which("afplay") else None


def available():
    """True when audio can be played at all. Rate is irrelevant to the check."""
    return stream_cmd(22050) is not None or file_player() is not None


NO_PLAYER = ("no audio player found — install pipewire-utils, alsa-utils, "
             "ffmpeg or sox (macOS has afplay already)")


def wav_bytes(pcm, rate):
    """Wrap raw s16le mono samples in a wav container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm)
    return buf.getvalue()


def write_temp_wav(pcm, rate):
    """A wav on disk for a file-only player. The caller unlinks it."""
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="claude-speak-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(wav_bytes(pcm, rate))
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


def play_blocking(pcm, rate):
    """Play one buffer, returning when it has finished. Used by the audition."""
    cmd = stream_cmd(rate)
    if cmd is not None:
        subprocess.run(cmd, input=pcm, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        return
    player = file_player()
    if player is None:
        raise RuntimeError(NO_PLAYER)
    path = write_temp_wav(pcm, rate)
    try:
        subprocess.run([player, path], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
