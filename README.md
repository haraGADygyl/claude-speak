# claude-speak

Claude Code reads its replies aloud, in a natural voice, entirely on your machine.

No API key, no cloud, no per-word billing. Speech is generated locally by
[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M), an 82M-parameter neural TTS
model, and it starts talking before the whole reply has finished rendering.

Built for people who'd rather listen than read a wall of text — and for anyone
whose eyes are done for the day.

```
/plugin marketplace add haraGADygyl/claude-speak
/plugin install claude-speak
```

Then, once, to fetch the voice model (~338 MB):

```
claude-speak install
```

Restart Claude Code and it starts talking.

---

## What you get

**A real voice, not a robot.** 54 Kokoro voices — American and British English
plus Spanish, French, Italian, Portuguese, Hindi, Japanese and Chinese. Hear the
best English ones and pick:

```
claude-speak audition
claude-speak voice bm_george
```

**It starts immediately.** A warm daemon keeps the model loaded, so there's no
2-second stall while something boots. Long replies are synthesized sentence by
sentence and start playing after the first one — roughly 30 ms from reply to
first audio.

**It reads prose, not punctuation.** Code blocks become *"Code block"* instead of
sixty seconds of syntax. `src/api/parser.py:42` becomes *"parser.py line 42"*.
URLs become *"link"*. Markdown, tables, and emoji are stripped.

**It knows which terminal is talking.** With several Claude Code sessions open,
a reply from another project waits its turn and introduces itself — *"From api
server. The migration finished…"* — instead of cutting off whatever is speaking.
A new reply from the *same* session does interrupt it, because that one is stale.

**It can wait until you're back.** Stepping away from a terminal:

```
claude-speak hold on
```

Replies stop being spoken. Each one is stashed and announced with a desktop
notification. When you return:

```
claude-speak play          # everything, oldest first, announced by project
claude-speak play api-server
claude-speak pending       # just look at what's waiting
```

---

## Controls

Every command works from a shell as `claude-speak …` or inside Claude Code as
`/speak …`.

| Command | What it does |
| --- | --- |
| `on` / `off` | Toggle reading replies aloud |
| `stop` | Shut up right now |
| `speed 1.2` | 0.5 slow → 1.5 fast |
| `voice af_bella` | Switch voice (and preview it) |
| `voices` | List all 54 |
| `audition` | Play the 10 best English voices back to back |
| `max 4000` | Characters read per reply before it stops |
| `hold on` / `off` | Stash replies instead of speaking them |
| `pending` / `play` / `clear` | Manage stashed replies |
| `mode queue` | Multi-terminal behaviour: `queue`, `interrupt`, `drop` |
| `queue` | What's speaking and what's waiting |
| `status` | Current settings |
| `restart` / `log` | Daemon control |

Inside Claude Code, `! claude-speak stop` is instant — the `!` prefix runs the
shell command without a model round trip, which matters when you want silence
*now*.

---

## Requirements

Linux is the tested platform. macOS works with the built-in `say` fallback;
Kokoro playback there needs `ffplay` or `sox`.

- `python3` and either `uv` or `python3-venv`
- `jq`
- `espeak-ng` — Kokoro uses it for phonemes
- An audio player: `paplay` (PipeWire/PulseAudio), `aplay`, `ffplay`, or `sox`
- Optional: `libnotify` (`notify-send`) for hold-mode notifications
- Optional: systemd — used to keep the daemon warm across reboots. Without it the
  daemon starts on first use and stays up for the login session.

Debian/Ubuntu:

```bash
sudo apt install python3-venv jq espeak-ng libnotify-bin
```

Without the model installed, claude-speak falls back to `spd-say` / `espeak-ng`
(Linux) or `say` (macOS). It works immediately; it just sounds robotic until you
run `claude-speak install`.

---

## How it works

```
Claude finishes a reply
        │
        ▼
  Stop hook  scripts/speak-hook.py        strips markdown, applies your settings
        │
        ▼
  Client     scripts/say.py               unix socket, ~30 ms, exits immediately
        │
        ▼
  Daemon     scripts/kokorod.py           model stays warm; synthesizes chunk by
        │                                 chunk and streams straight to the player
        ▼
  paplay / aplay / ffplay
```

The hook never blocks your session: it hands the text off and exits. If anything
in the chain fails, it fails silently rather than breaking Claude Code.

**Where things live** — deliberately outside the plugin directory, so a plugin
update never re-downloads 338 MB:

| Path | Contents |
| --- | --- |
| `~/.config/claude-speak/config.json` | Your settings |
| `~/.local/share/claude-speak/models/` | Kokoro model + voices |
| `~/.local/share/claude-speak/venv/` | Python environment |
| `~/.local/share/claude-speak/held.jsonl` | Replies waiting in hold mode |
| `$XDG_RUNTIME_DIR/claude-speak.sock` | Daemon socket |

Override with `CLAUDE_SPEAK_HOME` and `CLAUDE_SPEAK_CONFIG`.

---

## Known limits

**Auto-play when you focus a terminal isn't supported.** It was tried and it
doesn't work reliably: gnome-terminal runs every window and tab under a single
process, so there's no way to tell which session you're looking at, and Claude
Code rewrites the terminal title continuously so a marker can't be planted there
either. Hold mode with manual playback is the honest alternative. On terminals
that use one process per window (kitty, alacritty, foot) focus detection would be
feasible — PRs welcome.

**Wayland** is untested. Nothing in the audio path is X11-specific, so it likely
works; the notification path depends on your desktop.

**One voice at a time.** Speech is serialized by design. Two replies never
overlap.

---

## Uninstall

```
/plugin uninstall claude-speak
systemctl --user disable --now claude-speak.service
rm -rf ~/.local/share/claude-speak ~/.config/claude-speak
rm -f ~/.config/systemd/user/claude-speak.service
```

---

## Credits

- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) by hexgrad — Apache 2.0
- [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) by thewh1teagle — the
  ONNX runtime bindings and model releases this downloads

## License

MIT — see [LICENSE](LICENSE).
