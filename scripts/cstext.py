#!/usr/bin/env python3
"""Settings, and turning markdown into something worth listening to.

Shared by the Stop hook and `claude-speak read`, so a file you ask for aloud is
cleaned up exactly the way a reply is. Standard library only: the hook runs on
whatever python3 the system provides.

As a filter it cleans a file, or stdin when the path is "-":

    cstext.py notes.md
    git log -5 | cstext.py -
"""

import json
import os
import re
import sys

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
    # Replies are held by default: stashed with a notification rather than
    # spoken. Nothing ever starts talking unless you asked it to. Turn this off
    # (`claude-speak hold off`) to have replies read out as they finish.
    "holdReplies": True,
    "notify": True,
    # Short sound when a reply lands in hold mode. Path to an audio file, or
    # "off" for silence. Empty string picks a sensible system sound.
    "holdSound": "",
    # Never speak while something is recording from the microphone — you are on
    # a call. Applies even with holdReplies off, and suppresses the ding too, so
    # a meeting stays quiet. See `claude-speak guard`.
    "meetingGuard": True,
    # Recording apps that should NOT count as "in a meeting" (substring match,
    # case-insensitive), e.g. an always-on hotword listener.
    "meetingGuardIgnore": [],
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


def read_source(path):
    """A file, or stdin for "-". Binary is refused rather than read aloud."""
    if path == "-":
        data = sys.stdin.buffer.read()
    else:
        with open(path, "rb") as fh:
            data = fh.read()
    if b"\x00" in data:
        raise ValueError("looks like a binary file")
    return data.decode("utf-8", errors="replace")


def main():
    if len(sys.argv) != 2:
        print("usage: cstext.py <file>|-", file=sys.stderr)
        return 2
    try:
        raw = read_source(sys.argv[1])
    except (OSError, ValueError) as exc:
        print("cstext: %s: %s" % (sys.argv[1], exc), file=sys.stderr)
        return 1
    sys.stdout.write(clean(raw, load_config()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
