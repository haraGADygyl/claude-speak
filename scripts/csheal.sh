# Keeping the PATH link and the systemd unit pointed at the plugin in use.
#
# Both name an absolute path inside the plugin directory, and Claude Code
# stamps that directory with the version:
#
#   ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/
#
# An update writes a new one and leaves the old one on disk, so a link or a
# unit written at install time keeps resolving — to the previous release. The
# daemon is the one that hurts: a fix in kokorod.py never reaches a systemd
# user whose ExecStart still names the version they first installed, and the
# Stop hook goes on running the new code, so nothing looks broken.
#
# Repairs go *towards* $DATA/plugin-root, which the Stop hook rewrites
# whenever it runs from a directory it has not seen, and never towards the
# caller: an out-of-date claude-speak repairing things to point at itself
# would pin the daemon to the release it came from.
#
# Sourced by bin/claude-speak and scripts/install.sh. Nothing here prints;
# callers report in their own voice, from the status codes:
#
#   0  already correct     11  repaired
#   10 created             12  left alone, not ours
#   13 unit rewritten and the daemon restarted with it

cs_scripts_from_pointer() {          # <pointer file> -> scripts dir on stdout
  local pointer="$1" root
  [[ -s "$pointer" ]] || return 1
  root="$(head -n 1 "$pointer" 2>/dev/null)"
  [[ -n "$root" && -f "$root/kokorod.py" ]] || return 1
  printf '%s' "$root"
}

cs_record_root() {                   # <pointer file> <scripts dir>
  mkdir -p "$(dirname "$1")" 2>/dev/null || return 1
  printf '%s\n' "$2" > "$1"
}

# One copy of the unit. It used to be written only by install.sh; the CLI
# needs it too now, and two heredocs is how the config defaults drifted.
cs_unit_text() {                     # <venv python> <scripts dir>
  cat <<UNITEOF
[Unit]
Description=claude-speak TTS daemon (Kokoro)
After=pipewire.service pulseaudio.service

[Service]
Type=simple
ExecStart=$1 $2/kokorod.py
Restart=on-failure
RestartSec=3
Nice=5

[Install]
WantedBy=default.target
UNITEOF
}

cs_unit_write() {                    # <unit path> <venv python> <scripts dir>
  mkdir -p "$(dirname "$1")" 2>/dev/null || return 1
  cs_unit_text "$2" "$3" > "$1"
}

cs_unit_stale() {                    # true only when a unit exists and has drifted
  [[ -f "$1" ]] || return 1
  ! grep -qxF "ExecStart=$2 $3/kokorod.py" "$1"
}

cs_unit_sync() {                     # <unit path> <venv python> <scripts dir>
  cs_unit_stale "$@" || return 0
  cs_unit_write "$@" || return 1
  command -v systemctl >/dev/null 2>&1 || return 10
  systemctl --user daemon-reload >/dev/null 2>&1
  # Nothing to restart when the unit is not enabled: the daemon starts on the
  # next reply, and saying it is stopped is then the honest answer.
  systemctl --user is-enabled --quiet claude-speak.service 2>/dev/null || return 10
  systemctl --user restart claude-speak.service >/dev/null 2>&1 || return 10
  return 13
}

# A link worth repairing: one pointing into a claude-speak plugin directory,
# including one that has since been deleted. Anything else is somebody's own
# claude-speak and is left where it is.
cs_link_is_ours() {                  # <literal link target>
  local target="$1"
  [[ -f "$(dirname "$target")/../scripts/cspaths.py" ]] && return 0
  [[ ! -e "$target" && "$target" == *claude-speak*/bin/claude-speak ]] && return 0
  return 1
}

cs_link_sync() {                     # <bin dir> <scripts dir>
  local bindir="$1" want link current
  want="$(dirname "$2")/bin/claude-speak"
  [[ -x "$want" ]] || return 1
  link="$bindir/claude-speak"

  if [[ ! -e "$link" && ! -L "$link" ]]; then
    mkdir -p "$bindir" 2>/dev/null || return 1
    ln -s "$want" "$link" 2>/dev/null || return 1
    return 10
  fi

  # readlink is empty for a regular file, which is never ours to replace.
  current="$(readlink "$link" 2>/dev/null || true)"
  [[ -n "$current" ]] || current="$link"
  [[ "$current" == "$want" ]] && return 0
  cs_link_is_ours "$current" || return 12
  ln -sfn "$want" "$link" 2>/dev/null || return 1
  return 11
}
