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

Restart Claude Code, and you're set.

## Quiet by default

Nothing ever starts talking on its own. When a reply finishes you get a short
ding and a desktop notification; you hear it when *you* ask:

```
claude-speak play
```

That plays what *this* terminal produced; `play all` covers every project.
The quiet default exists because the alternative has a failure mode: a terminal
finishing mid-meeting and a voice announcing your code to a client. Two layers
prevent it.

**Replies are held.** They're stashed with a notification rather than spoken.
`claude-speak play` reads everything waiting, oldest first, each announced by
project. Prefer it to just talk? `claude-speak hold off`.

**The meeting guard.** Even with auto-speak on, nothing is spoken — and no ding
plays — while an application is recording from your microphone. If you're on a
call, you're not interrupted, whether or not you remembered to arm anything.

```
claude-speak guard test     # is the guard active right now, and what tripped it
claude-speak guard off      # disable it
```

It works by checking for live recording streams (PulseAudio/PipeWire source
outputs), so Zoom, Meet, Teams, Discord and browser calls all count. Playback
streams are a different thing entirely, so it never trips on its own audio.

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

**It waits until you're back.** This is the default. Replies are stashed and
announced rather than spoken, so nothing surprises you:

```
claude-speak play              # this terminal's project only
claude-speak play all          # every project, announced by name
claude-speak play api-server   # one named project
claude-speak pending           # what's waiting, * marks this terminal's
```

`play` defaults to the project you're standing in, so a terminal only ever
reads back its own work. The project name is announced only when you're
hearing more than one.

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
| `hold on` / `off` | Stash replies (default) or speak them as they finish |
| `guard on` / `off` / `test` | Never speak while your microphone is in use |
| `sound <file>` | Ding when a reply lands — `off`, `default`, or a path |
| `play` / `play all` / `play <project>` | Read stashed replies — this terminal, everything, or one project |
| `pending` / `clear` | List or discard stashed replies (same scoping) |
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
- Optional: `pactl` (pulseaudio-utils) — required by the meeting guard; without
  it the guard silently does nothing
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

**The meeting guard needs `pactl`.** It detects recording streams through
PulseAudio/PipeWire. On a system using bare ALSA or JACK it can't see anything
and stays inert — hold mode is the fallback there.

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
