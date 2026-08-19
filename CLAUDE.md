# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code plugin that reads Claude's replies aloud using a local neural TTS model (Kokoro via `kokoro-onnx`). Nothing leaves the machine at runtime. The repo is also its own plugin marketplace (`.claude-plugin/marketplace.json`), so **a push to `main` ships to anyone who installs or updates the plugin** — there is no separate release step.

## Commands

```bash
python3 -m unittest discover tests                      # everything (~1.5s)
python3 -m unittest tests.test_cstext.ShortenPaths      # one class
python3 -m unittest tests.test_cstext.Clean.test_lists_become_sentences   # one test

python3 scripts/cstext.py README.md      # what the cleaner produces — prints, never speaks
bash scripts/install.sh --no-service     # venv + 338 MB model, skipping the systemd unit
claude-speak restart | log | queue       # daemon control
```

No build, no linter, no CI. The tests need nothing installed and play no audio.

**Most other commands make real noise on the user's machine.** `claude-speak test|read|play|voice|speed|audition|install` and `say.py` all synthesize and play, and `claude-speak sound <file>` plays the file you hand it. Prefer `scripts/cstext.py` or the tests when verifying changes. To exercise the socket path without audio, bind a stub listener at `$XDG_RUNTIME_DIR/claude-speak.sock` — AF_UNIX paths cap near 108 bytes, so a deep scratchpad directory will fail to bind; use a short `/tmp` path.

## Two Python runtimes — the constraint that shapes everything

| Runs under | Files | May import |
| --- | --- | --- |
| System `python3` | `speak-hook.py`, `say.py`, `cstext.py`, `cspaths.py`, `csconfig.py`, `csaudio.py` | **stdlib only** |
| Venv `$DATA/venv/bin/python` | `kokorod.py`, `audition.py` | `numpy`, `kokoro_onnx` |

The Stop hook runs under whatever `python3` Claude Code happens to have and cannot see the venv. A third-party import anywhere in the first row breaks speech for every user — silently, for the reason below.

## Pipeline

```
Stop hook (hooks/hooks.json)
  → speak-hook.py    payload on stdin → cstext.clean() → hold or speak
  → say.py           unix-socket client, returns in ~30 ms
  → kokorod.py       warm model, sentence-chunked synthesis, streams PCM
  → paplay / pw-play / aplay / ffplay / sox — or afplay a wav at a time (macOS)
```

`speak-hook.py` wraps `main()` in a bare `except: pass` and always exits 0, because a broken hook must never break a Claude Code session. **Every failure is therefore invisible.** Debug by driving it directly:

```bash
export CLAUDE_SPEAK_HOME=/tmp/cs-test CLAUDE_SPEAK_CONFIG=/tmp/cs-test/config.json
printf '{"session_id":"s","cwd":"/tmp/proj","last_assistant_message":"hi"}' \
  | python3 scripts/speak-hook.py
```

Set those two env vars for anything that writes state. Without them you scribble on the user's real config and their queue of held replies.

## State lives outside the plugin directory

`cspaths.py` is the only place paths are defined. Runtime state sits in `~/.local/share/claude-speak/` and `~/.config/claude-speak/` deliberately: a plugin update replaces the plugin directory, and the 338 MB model has to survive that.

## Adding a config setting means editing one file

`DEFAULTS` in `scripts/cstext.py`, and nothing else. `scripts/csconfig.py` writes it out, and `ensure_cfg` in `bin/claude-speak` runs `csconfig.py config ensure` on every invocation, so an upgrade adds new keys without touching choices the user already made.

The one exception is display: `claude-speak status` prints the keys named in `SUMMARY_KEYS` in `scripts/csconfig.py`, so a new setting exists and is honoured without being listed there, but stays invisible in the status block until it is added.

It used to be three files — the Python dict plus a `DEFAULT_CFG` heredoc in `bin/claude-speak` and another in `install.sh` — and they drifted, which is how `fallbackRate` and `fallbackVoice` stayed absent for four releases. `NoDuplicateDefaults` in the tests fails if a JSON heredoc reappears in either shell file.

## The shell shells out for JSON

`bin/claude-speak` uses no `jq`. Every read, write and held-reply query goes through `scripts/csconfig.py` (`config get|set|ensure|summary`, `held count|labels|pending|text|drop`). python3 is a hard dependency of the plugin already, so this removed a system package rather than adding one. `NoDuplicateDefaults.test_the_shell_does_not_need_jq` keeps it that way.

## Behaviour that looks like a bug but is deliberate

- **Quiet by default.** `holdReplies` is true: replies are appended to `held.jsonl` (O_APPEND, so concurrent sessions don't interleave) and announced with a ding, not spoken. `claude-speak play` reads them back.
- **The meeting guard outranks every other setting.** If `pactl list source-outputs` shows a recording stream, the reply is held with *no* sound at all — the ding is suppressed too.
- **Hold scoping is by directory basename.** The hook labels each reply `basename(cwd)`; `play`/`clear`/`pending` default to that label, which is how one terminal reads back only its own project.
- **Multi-session:** the same `session_id` interrupts itself (that reply is stale); a different session queues behind and is introduced as "From \<project\>".
- **The spoken queue holds three.** `MAX_QUEUE` in `kokorod.py` caps waiting replies at 3 and drops the *oldest* beyond that, so a fourth terminal finishing during a long reply loses the first one. Held replies (`held.jsonl`) have no such cap — this applies only to speech in flight.

## The text cleaner is the fragile part

`clean()` in `scripts/cstext.py` turns markdown into speech, and its regexes have caused every behavioural bug in this repo so far:

- Line-anchored rules must use `[ \t]` for indentation, **never `\s`**. Under `re.MULTILINE`, `\s*` reaches backwards over the blank line above and eats the paragraph break — the very thing that later becomes a full stop.
- The path rule must leave `and/or`, `TCP/IP` and `24/7` alone. That is why a *relative* path is only recognised when it ends in a file extension; a rooted path (`/`, `~/`, `./`, `../`) has no such requirement.

Any change here needs a case in `tests/test_cstext.py`, including the ones that must *not* change.

## Surfaces to keep in sync

Adding a user-visible command touches four places:

1. `bin/claude-speak` — the `case` branch, the header comment (which *is* the `--help` output, printed by awk up to the first non-comment line), and the unknown-option list
2. `skills/speak/SKILL.md` — `argument-hint` and the valid-arguments line. This is the `/speak` slash command; it has `disable-model-invocation: true` and runs the binary via `!` frontmatter, so Claude's whole job is to report the result in one line
3. `README.md` — the Controls table
4. `.claude-plugin/plugin.json` — **bump `version` in the same commit.** Every release so far has done this: minor for a feature, patch for a fix

## Releasing

The version bump *is* the release. Three steps after pushing it:

```bash
# 1. tag — refuses to run unless plugin.json and the marketplace entry agree,
#    which is the check worth having, since the two are edited separately
claude plugin tag -m "claude-speak %s — <one line>" --push     # --dry-run first

# 2. release notes — write them to a file, then
gh release create claude-speak--v<version> --verify-tag \
  --title "<version> — <two or three words>" --notes-file <path>

# 3. ship it
claude plugin update claude-speak@claude-speak                 # bare name fails
```

Write the notes for someone who *uses* the plugin: what changed in what they hear, not which file moved. The commit bodies are the source — `--notes-from-tag` only picks up the one-line annotation. Past releases are the model for length and tone.

Two traps, both hit while backfilling the first seven:

- `--verify-tag` followed by an empty argument makes `gh` read `""` as an asset path and fail with `stat : no such file or directory`. Watch for empty shell variables in that position
- `gh` marks **Latest** by creation time, not version. Releasing in order is fine; a bulk backfill needs `gh release edit <tag> --latest` afterwards

Tags run back to 0.1.0, each marking the last commit carrying that version — except `v0.3.0`, cut at `f7888ac`, because the three commits after it shipped the `read` feature without a bump and belong to the 0.4.0 range.

A session restart is needed after step 3 for the Stop hook to pick up the new code.

## Commit style

Conventional Commits, enforced by `.githooks/commit-msg`. Enable it once per clone — git does not version-control `.git/hooks`:

```bash
git config core.hooksPath .githooks
```

```
<type>[optional scope][!]: <description>     # 72 chars max, ! marks a breaking change

feat(cli): read any file aloud with claude-speak read
fix(cleaner): keep the paragraph break before a heading
chore(release): 0.4.0
```

Types: `feat fix docs style refactor perf test build ci chore revert`. Scope is free-form; `cleaner`, `hook`, `daemon`, `cli` match the layout here.

The body keeps this repo's existing shape: blank line, a paragraph on **why**, then bullets on what. Merge, revert and `fixup!`/`squash!` subjects are passed through untouched. `git commit --no-verify` bypasses the hook; `tests/test_commit_msg.py` covers it.

Commits before `d3de1cd` predate the convention and do not follow it. History is public — do not rewrite it to match.
