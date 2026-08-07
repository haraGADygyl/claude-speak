#!/usr/bin/env bash
# One-time setup: python venv, Kokoro model download, optional systemd service.
# Safe to re-run; existing pieces are skipped.
set -uo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${CLAUDE_SPEAK_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/claude-speak}"
CFG="${CLAUDE_SPEAK_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/claude-speak/config.json}"
MODELS="$DATA/models"
VENV="$DATA/venv"
RELEASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m warn:\033[0m %s\n' "$*"; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- prereqs ---
say "Checking prerequisites"
command -v jq >/dev/null || warn "jq not found — install it (apt install jq) or the CLI won't run"
command -v espeak-ng >/dev/null || command -v espeak >/dev/null \
  || warn "espeak-ng not found — Kokoro needs it for phonemes (apt install espeak-ng)"
command -v paplay >/dev/null || command -v aplay >/dev/null || command -v ffplay >/dev/null \
  || warn "no audio player found — install pipewire-utils, alsa-utils, or ffmpeg"

PYBOOT=""
for c in uv python3; do command -v "$c" >/dev/null && { PYBOOT="$c"; break; }; done
[[ -n "$PYBOOT" ]] || die "need uv or python3 to build the virtualenv"

# ------------------------------------------------------------------ venv ----
if [[ -x "$VENV/bin/python" ]]; then
  say "Virtualenv already present at $VENV"
else
  say "Creating virtualenv at $VENV"
  mkdir -p "$DATA"
  if command -v uv >/dev/null; then
    uv venv "$VENV" --python 3.12 >/dev/null || die "uv venv failed"
    uv pip install --python "$VENV/bin/python" kokoro-onnx soundfile numpy >/dev/null \
      || die "dependency install failed"
  else
    python3 -m venv "$VENV" || die "python3 -m venv failed (apt install python3-venv)"
    "$VENV/bin/pip" install --quiet --upgrade pip >/dev/null
    "$VENV/bin/pip" install --quiet kokoro-onnx soundfile numpy \
      || die "dependency install failed"
  fi
fi

# ----------------------------------------------------------------- model ----
mkdir -p "$MODELS"
fetch() {  # fetch <url> <dest> <human size>
  local url="$1" dest="$2" size="$3"
  if [[ -s "$dest" ]]; then say "$(basename "$dest") already downloaded"; return; fi
  say "Downloading $(basename "$dest") ($size)"
  if command -v curl >/dev/null; then
    curl -L --fail --progress-bar -o "$dest.part" "$url" || { rm -f "$dest.part"; die "download failed"; }
  else
    wget -q --show-progress -O "$dest.part" "$url" || { rm -f "$dest.part"; die "download failed"; }
  fi
  mv "$dest.part" "$dest"
}
fetch "$RELEASE/kokoro-v1.0.onnx" "$MODELS/kokoro-v1.0.onnx" "311 MB"
fetch "$RELEASE/voices-v1.0.bin"  "$MODELS/voices-v1.0.bin"  "27 MB"

# ---------------------------------------------------------------- config ----
if [[ ! -f "$CFG" ]]; then
  mkdir -p "$(dirname "$CFG")"
  # Carry over settings from a hand-rolled install, if the user had one.
  if [[ -f "$HOME/.claude/speak.json" ]] && command -v jq >/dev/null; then
    say "Importing settings from ~/.claude/speak.json"
    jq '{enabled, engine, voice: (.kokoroVoice // .voice // "af_heart"),
         speed: (.kokoroSpeed // .speed // 1.0), maxChars, announceCode,
         shortenPaths, multiSession, holdReplies, notify}' \
       "$HOME/.claude/speak.json" >"$CFG" 2>/dev/null || rm -f "$CFG"
  fi
  [[ -f "$CFG" ]] || cat >"$CFG" <<'JSON'
{
  "enabled": true,
  "engine": "auto",
  "voice": "af_heart",
  "speed": 1.0,
  "maxChars": 2500,
  "announceCode": true,
  "shortenPaths": true,
  "multiSession": "queue",
  "holdReplies": true,
  "notify": true,
  "holdSound": "",
  "meetingGuard": true,
  "meetingGuardIgnore": [],
  "fallbackRate": 25,
  "fallbackVoice": "female1"
}
JSON
  say "Wrote config to $CFG"
fi

# --------------------------------------------------------------- systemd ----
# Optional: keeps the model warm across reboots. Without it the daemon starts
# on first use and stays up for the rest of the login session.
if [[ "${1:-}" != "--no-service" ]] && command -v systemctl >/dev/null \
   && systemctl --user show-environment >/dev/null 2>&1; then
  UNIT="$HOME/.config/systemd/user/claude-speak.service"
  mkdir -p "$(dirname "$UNIT")"
  cat >"$UNIT" <<UNITEOF
[Unit]
Description=claude-speak TTS daemon (Kokoro)
After=pipewire.service pulseaudio.service

[Service]
Type=simple
ExecStart=$VENV/bin/python $SCRIPTS/kokorod.py
Restart=on-failure
RestartSec=3
Nice=5

[Install]
WantedBy=default.target
UNITEOF
  systemctl --user daemon-reload
  systemctl --user enable --now claude-speak.service >/dev/null 2>&1 \
    && say "Daemon enabled (systemd user service)" \
    || warn "could not enable the systemd service; the daemon will start on demand"
else
  say "Skipping systemd service; the daemon starts on demand"
fi

# ------------------------------------------------------------------ done ----
say "Testing"
python3 "$SCRIPTS/say.py" --voice "$( command -v jq >/dev/null && jq -r .voice "$CFG" || echo af_heart )" \
  "Claude speak is installed. This is the voice your replies will use when you play them."

cat <<'DONE'

Done. Useful commands:

Replies are HELD by default -- you get a ding and a notification, and
hear them when you ask:

  claude-speak play         read everything waiting, oldest first
  claude-speak hold off     or have replies spoken automatically

Even with auto-speak on, nothing is spoken while your microphone is in
use, so a call is never interrupted (claude-speak guard test).

  claude-speak audition     hear the 10 best English voices, then pick one
  claude-speak voice bm_george
  claude-speak speed 1.2

The same controls exist in Claude Code as /speak (for example "/speak
play"). Restart Claude Code once so the Stop hook loads.
DONE
