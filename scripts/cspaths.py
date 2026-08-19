"""Shared locations for claude-speak.

Runtime state deliberately lives outside the plugin directory: plugin updates
replace that directory, and a 338 MB model download should survive them.
"""

import os

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


def kokoro_ready():
    return all(os.path.exists(p) for p in (VENV_PY, MODEL, VOICES))
