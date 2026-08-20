"""Shared locations for claude-speak.

Runtime state deliberately lives outside the plugin directory: plugin updates
replace that directory, and a 338 MB model download should survive them.
"""

import os
import re

HOME = os.path.expanduser("~")

_XDG_DATA = os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share")
_XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")

DATA = os.environ.get("CLAUDE_SPEAK_HOME") or os.path.join(_XDG_DATA, "claude-speak")
CONFIG = os.environ.get("CLAUDE_SPEAK_CONFIG") or os.path.join(
    _XDG_CONFIG, "claude-speak", "config.json")

VENV_PY = os.path.join(DATA, "venv", "bin", "python")
MODEL = os.path.join(DATA, "models", "kokoro-v1.0.onnx")
VOICES = os.path.join(DATA, "models", "voices-v1.0.bin")
HELD = os.path.join(DATA, "held.jsonl")
LAST = os.path.join(DATA, "last")           # one file per project, see last_file
LOG = os.path.join(DATA, "daemon.log")

# Where the plugin is installed right now, recorded by the Stop hook because it
# is the only part that always runs from the current copy. Claude Code stamps
# the plugin directory with the version, so it moves on every update, and both
# the PATH link and the systemd unit name it absolutely — see scripts/csheal.sh.
ROOT_POINTER = os.path.join(DATA, "plugin-root")

# A socket under XDG_RUNTIME_DIR is cleaned up on logout; fall back for systems
# that do not set it (some containers, some BSD-ish setups).
_RUNTIME = os.environ.get("XDG_RUNTIME_DIR") or DATA
SOCK = os.path.join(_RUNTIME, "claude-speak.sock")

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
DAEMON = os.path.join(SCRIPTS, "kokorod.py")


def last_file(label):
    """Where the most recent reply from one project is kept, for `again`.

    The label is a directory basename, so it can hold anything a directory
    name can — spaces, dots, a leading dash. Everything outside a safe set
    becomes an underscore: that can land two oddly-named projects on one
    file, which is a fair price for not letting a directory called ".." write
    wherever it likes.
    """
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", label or "").strip(".") or "claude"
    return os.path.join(LAST, safe + ".txt")


def kokoro_ready():
    return all(os.path.exists(p) for p in (VENV_PY, MODEL, VOICES))
