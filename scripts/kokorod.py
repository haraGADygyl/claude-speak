#!/usr/bin/env python3
"""Kokoro TTS daemon — keeps the model warm and streams speech as it renders.

Listens on a unix socket for newline-delimited JSON commands:
    {"cmd": "say", "text": "...", "voice": "af_heart", "speed": 1.0,
     "session": "<id>", "label": "myproject", "mode": "queue"}
    {"cmd": "stop"}     cancel everything, drop the queue
    {"cmd": "status"}

Multi-session behaviour, with several Claude Code terminals sharing one daemon:

  * A new reply from the SAME session interrupts it — you told Claude to start
    over, so the old reply is stale.
  * A reply from a DIFFERENT session queues behind whatever is speaking and is
    announced by project name. Nothing overlaps, nothing is silently lost.
"""

import collections
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cspaths  # noqa: E402

CHUNK_CHARS = 260   # synthesis granularity; playback starts after chunk 1
MAX_QUEUE = 3       # waiting replies; oldest is dropped beyond this


def split_chunks(text, limit=CHUNK_CHARS):
    parts = re.split(r"(?<=[.!?:;])\s+", text)
    chunks, cur = [], ""
    for part in parts:
        while len(part) > limit:                  # a single monster sentence
            cut = part.rfind(" ", 0, limit) or limit
            chunks.append(part[:cut].strip())
            part = part[cut:]
        if len(cur) + len(part) + 1 <= limit:
            cur = (cur + " " + part).strip()
        else:
            if cur:
                chunks.append(cur)
            cur = part.strip()
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c]


def player_cmd(rate):
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
    raise RuntimeError("no audio player found (install pipewire, alsa-utils, "
                       "ffmpeg or sox)")


class Job(object):
    __slots__ = ("session", "label", "text", "voice", "speed")

    def __init__(self, msg):
        self.session = msg.get("session") or "default"
        self.label = (msg.get("label") or "").strip()
        self.text = msg["text"]
        self.voice = msg.get("voice") or "af_heart"
        self.speed = float(msg.get("speed") or 1.0)


class Speaker:
    def __init__(self, kokoro):
        self.kokoro = kokoro
        self.cv = threading.Condition()
        self.queue = collections.deque()
        self.current = None
        self.cancel = False
        self.player = None
        self.last_label = None
        self.seen_labels = set()
        threading.Thread(target=self._worker, daemon=True).start()

    # ---- caller side -----------------------------------------------------

    def submit(self, job, mode="queue"):
        with self.cv:
            if job.label:
                self.seen_labels.add(job.label)
            same_session = self.current is not None and self.current.session == job.session

            if mode == "interrupt":
                self.queue.clear()
                self._cancel_locked()
            elif mode == "drop" and not same_session and (
                    self.current is not None or self.queue):
                return "dropped"
            else:                                     # queue
                # A newer reply from a session supersedes its own waiting ones.
                self.queue = collections.deque(
                    j for j in self.queue if j.session != job.session)
                if same_session:
                    self._cancel_locked()

            self.queue.append(job)
            while len(self.queue) > MAX_QUEUE:
                self.queue.popleft()
            self.cv.notify()
        return "queued"

    def stop(self):
        with self.cv:
            self.queue.clear()
            self._cancel_locked()

    def status(self):
        with self.cv:
            return {"speaking": self.current.label if self.current else None,
                    "queued": [j.label for j in self.queue],
                    "sessions_seen": sorted(self.seen_labels)}

    def _cancel_locked(self):
        self.cancel = True
        proc, self.player = self.player, None
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    # ---- worker side -----------------------------------------------------

    def _worker(self):
        while True:
            with self.cv:
                while not self.queue:
                    self.cv.wait()
                job = self.queue.popleft()
                self.current = job
                self.cancel = False
            try:
                self._speak(job)
            except Exception as exc:
                print("speak error: %r" % (exc,), file=sys.stderr, flush=True)
            with self.cv:
                self.current = None

    def _announce(self, job):
        """Name the terminal a reply came from, once the answer is ambiguous."""
        if not job.label or len(self.seen_labels) < 2 or job.label == self.last_label:
            return ""
        return "From %s. " % job.label.replace("-", " ").replace("_", " ")

    def _speak(self, job):
        text = self._announce(job) + job.text
        self.last_label = job.label
        player = None
        try:
            for chunk in split_chunks(text):
                if self.cancel:
                    return
                try:
                    samples, rate = self.kokoro.create(
                        chunk, voice=job.voice, speed=job.speed)
                except Exception as exc:      # bad voice, phonemizer hiccup
                    print("synth error: %r" % (exc,), file=sys.stderr, flush=True)
                    continue
                if self.cancel:
                    return

                if player is None:
                    player = subprocess.Popen(
                        player_cmd(rate), stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    with self.cv:
                        if self.cancel:
                            player.kill()
                            return
                        self.player = player

                pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
                try:
                    player.stdin.write(pcm)
                    player.stdin.flush()
                except (BrokenPipeError, ValueError, OSError):
                    return
        finally:
            if player is not None:
                try:
                    player.stdin.close()
                    player.wait(timeout=300)   # let the queue wait its turn
                except (BrokenPipeError, ValueError, OSError,
                        subprocess.TimeoutExpired):
                    pass
                with self.cv:
                    if self.player is player:
                        self.player = None


def handle(conn, speaker):
    with conn:
        conn.settimeout(5)
        data = b""
        try:
            while b"\n" not in data:
                part = conn.recv(65536)
                if not part:
                    break
                data += part
        except socket.timeout:
            return

        reply = b"ok\n"
        for line in data.split(b"\n"):
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            cmd = msg.get("cmd")
            if cmd == "say":
                if (msg.get("text") or "").strip():
                    reply = (speaker.submit(Job(msg),
                                            msg.get("mode") or "queue") + "\n").encode()
            elif cmd == "stop":
                speaker.stop()
            elif cmd == "status":
                reply = (json.dumps(speaker.status()) + "\n").encode()
        try:
            conn.sendall(reply)
        except OSError:
            pass


def main():
    from kokoro_onnx import Kokoro

    kokoro = Kokoro(cspaths.MODEL, cspaths.VOICES)
    kokoro.create("ready", voice="af_heart", speed=1.0)   # warm the graph
    speaker = Speaker(kokoro)

    if os.path.exists(cspaths.SOCK):
        os.unlink(cspaths.SOCK)
    os.makedirs(os.path.dirname(cspaths.SOCK), exist_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(cspaths.SOCK)
    os.chmod(cspaths.SOCK, 0o600)
    server.listen(8)
    print("claude-speak daemon ready on %s" % cspaths.SOCK, flush=True)

    try:
        while True:
            conn, _ = server.accept()
            threading.Thread(target=handle, args=(conn, speaker), daemon=True).start()
    finally:
        server.close()
        if os.path.exists(cspaths.SOCK):
            os.unlink(cspaths.SOCK)


if __name__ == "__main__":
    main()
