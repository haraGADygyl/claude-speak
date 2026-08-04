#!/usr/bin/env python3
"""Stop hook: read Claude's last reply aloud.

Runs on the system python (standard library only). Takes the hook payload on
stdin, extracts the final text reply, strips markdown down to something worth
listening to, and hands it off without blocking the session.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cspaths  # noqa: E402

DEFAULTS = {
    "enabled": True,
    "engine": "auto",           # auto | kokoro | say | spd-say | espeak-ng
    "voice": "af_heart",
    "speed": 1.0,
    "maxChars": 2500,
    "announceCode": True,       # say "Code block" instead of reading code
    "shortenPaths": True,       # /a/b/c/file.py:42 -> "file.py line 42"
    # Several Claude Code terminals sharing one daemon:
    #   queue     — finish the current reply, then the next, announcing whose it is
    #   interrupt — the newest reply always cuts off whatever is speaking
    #   drop      — ignore replies arriving while another session speaks
    "multiSession": "queue",
    # Stepping away: stash replies + desktop notification instead of speaking.
    "holdReplies": False,
    "notify": True,
    # Fallback engine tuning (only used when Kokoro is not installed).
    "fallbackRate": 25,
    "fallbackVoice": "female1",
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(cspaths.CONFIG) as fh:
            cfg.update(json.load(fh))
    except (OSError, ValueError):
        pass
    return cfg


def last_assistant_text(payload):
    """Prefer the payload field; fall back to parsing the transcript."""
    direct = payload.get("last_assistant_message")
    if isinstance(direct, str) and direct.strip():
        return direct

    path = payload.get("transcript_path") or ""
    if not path or not os.path.exists(path):
        return ""

    found = ""
    with open(path, errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") != "assistant":
                continue
            content = entry.get("message", {}).get("content")
            if not isinstance(content, list):
                continue
            chunks = [b.get("text", "") for b in content
                      if isinstance(b, dict) and b.get("type") == "text"]
            text = "\n".join(c for c in chunks if c.strip())
            if text.strip():
                found = text  # last one wins
    return found


EMOJI = re.compile("[\U0001f000-\U0001faff←-⇿⌀-➿⬀-⯿️]")


def clean(text, cfg):
    marker = " . Code block. " if cfg["announceCode"] else " "
    text = re.sub(r"```.*?```", marker, text, flags=re.DOTALL)
    text = re.sub(r"```.*", marker, text, flags=re.DOTALL)      # unterminated fence

    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)      # links keep the label
    text = re.sub(r"https?://\S+", " link ", text)

    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*([-*_])\s*\1\s*\1[\s\1]*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)[*_]([^*_\n]+)[*_](?!\w)", r"\1", text)

    text = re.sub(r"^\s*[-*+]\s+", ". ", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+[.)]\s+", ". ", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\|.*\|\s*$", " ", text, flags=re.MULTILINE)   # table rows

    if cfg["shortenPaths"]:
        text = re.sub(
            r"(?:~|\.{0,2})?/(?:[\w.\-]+/){1,}([\w.\-]+)(?::(\d+))?",
            lambda m: m.group(1) + (" line " + m.group(2) if m.group(2) else ""),
            text,
        )

    text = EMOJI.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", ". ", text)
    text = text.replace("\n", " ")
    text = re.sub(r"(\.\s*){2,}", ". ", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    return text.strip()


def notify(title, body):
    if shutil.which("notify-send"):
        cmd = ["notify-send", "-a", "Claude Code", "-i", "utilities-terminal",
               # Collapse repeats into one notification instead of a stack.
               "-h", "string:x-canonical-private-synchronous:claude-speak",
               title, body]
    elif platform.system() == "Darwin" and shutil.which("osascript"):
        cmd = ["osascript", "-e",
               'display notification "%s" with title "%s"' % (body, title)]
    else:
        return
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def hold(text, cfg):
    """Stash the reply for later playback and say that it is waiting."""
    entry = {"ts": time.time(), "session": cfg["_session"],
             "label": cfg["_label"], "text": text}
    try:
        os.makedirs(os.path.dirname(cspaths.HELD), exist_ok=True)
        # O_APPEND keeps concurrent sessions from interleaving mid-line.
        fd = os.open(cspaths.HELD, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps(entry, ensure_ascii=False) + "\n").encode())
        finally:
            os.close(fd)
    except OSError:
        return

    if not cfg["notify"]:
        return
    waiting = 0
    try:
        with open(cspaths.HELD) as fh:
            waiting = sum(1 for ln in fh if ln.strip())
    except OSError:
        pass
    notify("Claude · %s" % cfg["_label"],
           "Reply ready — %d waiting. Run: claude-speak play" % waiting)


def pick_engine(cfg):
    want = cfg["engine"]
    if want != "auto":
        return want
    if cspaths.kokoro_ready():
        return "kokoro"
    if platform.system() == "Darwin" and shutil.which("say"):
        return "say"
    for candidate in ("spd-say", "espeak-ng", "espeak"):
        if shutil.which(candidate):
            return candidate
    return ""


def speak(text, cfg):
    engine = pick_engine(cfg)
    if not engine:
        return

    if engine == "kokoro":
        if cspaths.kokoro_ready():
            # The daemon streams chunk by chunk. Session identity lets it
            # interrupt only this session and queue other terminals behind us.
            subprocess.Popen(
                [sys.executable, os.path.join(cspaths.SCRIPTS, "say.py"),
                 "--voice", str(cfg["voice"]),
                 "--speed", str(cfg["speed"]),
                 "--session", cfg["_session"],
                 "--label", cfg["_label"],
                 "--mode", str(cfg["multiSession"]),
                 text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            return
        engine = "say" if platform.system() == "Darwin" else "spd-say"

    if engine == "say":                                  # macOS built-in
        subprocess.run(["pkill", "-x", "say"], check=False)
        args = ["say", "-r", str(int(180 * float(cfg["speed"]))), text]
    elif engine == "spd-say":
        subprocess.run(["spd-say", "-C"], check=False)    # stop previous reply
        args = ["spd-say", "-r", str(cfg["fallbackRate"]),
                "-t", str(cfg["fallbackVoice"]), "-m", "some", text]
    else:                                                # espeak-ng / espeak
        subprocess.run(["pkill", "-f", "^espeak"], check=False)
        args = [engine, "-s", str(150 + int(cfg["fallbackRate"])), text]

    subprocess.Popen(args, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}

    cfg = load_config()
    if not cfg["enabled"]:
        return

    # Identify the terminal this reply came from, so concurrent sessions can be
    # kept apart instead of talking over each other.
    cfg["_session"] = str(payload.get("session_id") or os.getppid())
    cwd = payload.get("cwd") or os.getcwd()
    cfg["_label"] = os.path.basename(cwd.rstrip("/")) or "claude"

    text = clean(last_assistant_text(payload), cfg)
    if not text:
        return

    limit = int(cfg["maxChars"])
    if len(text) > limit:
        cut = text.rfind(".", 0, limit)
        text = text[: cut + 1 if cut > limit // 2 else limit] + " . Rest is on screen."

    hold(text, cfg) if cfg["holdReplies"] else speak(text, cfg)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # a broken hook must never break the session
    sys.exit(0)
