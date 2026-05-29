# Clean-macOS-VM bootstrap test

Manual verification for parent change `hermes-agent-installer` tasks **6.5** and
**12.7**: a fresh macOS VM survives `curl … | bash`, `hermes verify` is clean,
and the bundled plugins respond to a basic smoke check.

Two flows to exercise:

| Flow | Trigger | Expected install scope |
|------|---------|------------------------|
| **A — Zero-config (factory)** | `curl … | bash` only | `vision` skill + `macos-control` + `voice` (no secrets) |
| **B — BYO-config (private)** | `HERMES_CONFIG_URL=… curl … | bash` | everything in the private `hermes_config` (incl. `telegram-bot`, `backups`) |

> Either start two VMs or reset between flows. The factory install leaves a
> functioning Hermes; flow B is purely additive *only if* the private config
> registers a superset.

---

## 0. Prepare the VM

- macOS Ventura (13) or newer, 4 GB RAM / 30 GB disk minimum.
- VM tool: UTM (Apple Silicon ARM image) or Multipass (`multipass launch --vm`
  isn't macOS; use UTM/VMware Fusion/Parallels).
- After first boot: complete Setup Assistant, sign in to the user account,
  open **Terminal**.
- Confirm:
  ```sh
  sw_vers -productVersion
  uname -m
  ```
  Expect: a macOS version like `14.x` and `arm64` (Apple Silicon) or `x86_64`.

---

## Flow A — Zero-config (factory)

### A.1 Bootstrap

```sh
curl -fsSL https://raw.githubusercontent.com/Dmitriy403/hermes_setup/main/install.sh | bash
```

Expected log lines (in order, allowing for `unchanged:` skips):

```
==> Homebrew not found — installing                  (first time only)
==> Installing prerequisites via Homebrew            (python, git, node, pipx)
==> Installing the Claude Code CLI                   (npm -g)
==> Cloning https://github.com/Dmitriy403/hermes_setup.git → ~/.hermes_setup
==> Installing the hermes CLI via pipx (editable)
==> Factory install — no secrets required for the default plugins.
==> Setup complete.
Run "hermes install" now? [y/N]
```

Answer **y**. Then expect:

```
==> manifest validated
==> probe-tcc present
... (file/skill writes for vision; no claude_md/settings/keybindings)
unchanged: plugin macos-control (console-script present)   ← only on re-runs
warn: plugin voice pre-reqs missing — `brew install whisper-cpp ffmpeg`
pipx inject macos-control … --include-apps
pipx inject voice … --include-apps
```

No `pipx inject telegram-bot` / `backup`. No `launchctl load …` lines (neither
`macos-control` nor `voice` declares a launchd job).

✅ **Gate A.1 passes** if exit status is 0 and the `warn: … voice …` line shows up.

### A.2 Console scripts on PATH

```sh
which hermes hermes-macos-control hermes-voice
```

All three resolve into `~/.local/bin/`.

> If `which hermes` fails, run `pipx ensurepath`, open a new shell.

### A.3 Verify (pre-TCC)

```sh
hermes verify
```

Expected drift (everything else `match`):

- `brew-deps voice  missing  `brew install whisper-cpp ffmpeg``
- No `plugin-package` / `launchd` drift.
- Possibly TCC-related warnings if any vision/macos-control component checks
  permissions, but `verify` itself **does not** inspect TCC state — that is
  `hermes doctor`'s job.

### A.4 Fix the voice pre-reqs

```sh
brew install whisper-cpp ffmpeg
hermes verify
```

Now `brew-deps voice match`. `hermes verify` returns clean.

✅ **Gate A.4 passes** when `hermes verify` reports zero non-match records.

### A.5 TCC walkthrough

```sh
hermes doctor
```

Expected: lists Screen Recording + Accessibility as **not granted** for the
responsible terminal app (Terminal.app / iTerm.app), with deep-link URLs.

```sh
hermes doctor --fix
```

This opens each System Settings pane. Grant the categories, **quit and
re-open** Terminal so the new responsible-process bind takes effect, then:

```sh
hermes doctor
```

Expected: every category `granted`.

### A.6 Smoke-test the factory plugins

> The console scripts (`hermes-macos-control`, `hermes-voice`) are
> MCP-server entrypoints — running them with no args waits on stdin for an
> MCP client. Don't try `--help`. Instead, verify the packages are importable
> in the hermes venv and exercise their real entry points via Python.

**`macos-control`** — module installed:

```sh
~/.local/pipx/venvs/hermes/bin/python -c "import macos_control.server, macos_control.tools; print('macos_control OK')"
```

Expected: `macos_control OK`.

**`voice`** — module installed + one real transcription (whisper-cpp + ffmpeg
already installed in A.4):

```sh
~/.local/pipx/venvs/hermes/bin/python -c \
  "from voice.server import transcribe; \
   import json; print(json.dumps(transcribe('/System/Library/Sounds/Glass.aiff')))"
```

Expected: `{"ok": true, "backend": "local", "text": "<empty or short>", …}`
— the clip is a short chime so the text may be blank; `ok: true` is the
success signal. The whisper model auto-downloads on first call (~140 MB
for `base`); allow a minute on the first run.

**`vision`** — skill, invoked through Claude. In a Claude Code session inside
the VM:

```
> describe the image at /System/Library/Desktop\ Pictures/Monterey.heic
```

Expected: Claude returns a description (validates the skill is registered and
callable). Skip if Claude Code isn't signed in on the VM.

✅ **Gate A passes** when all three plugins respond.

---

## Flow B — BYO-config (private repo)

> Pre-reqs: an SSH key on the VM with **read** access to the private
> `hermes_config` repo (or use an HTTPS URL with a fine-scoped PAT), and a
> prepared `secrets.env` file containing the real TELEGRAM_BOT_TOKEN,
> TELEGRAM_ALLOWED_CHAT_IDS, RESTIC_PASSWORD, etc.

### B.1 Bootstrap with private config

```sh
HERMES_CONFIG_URL=git@github.com:Dmitriy403/hermes_config.git \
HERMES_SECRETS_FILE=/path/on/vm/to/secrets.env \
curl -fsSL https://raw.githubusercontent.com/Dmitriy403/hermes_setup/main/install.sh | bash
```

Expected new lines vs. Flow A:

```
==> Cloning git@github.com:Dmitriy403/hermes_config.git → ~/hermes_config
==> Using private config root: /Users/<you>/hermes_config
==> Copying secrets from /path/.../secrets.env → /Users/<you>/hermes_config/secrets.env
```

When `hermes install` runs (it picks up `--manifest-dir ~/hermes_config`):

```
pipx inject telegram-bot … --include-apps
pipx inject backups … --include-apps
warn: plugin backups pre-reqs missing — `brew install restic`   (if restic absent)
write: ~/Library/LaunchAgents/com.hermes.telegram-bot.plist
launchctl load com.hermes.telegram-bot
write: ~/Library/LaunchAgents/com.hermes.backup.plist
launchctl load com.hermes.backup
```

✅ **Gate B.1 passes** if both plists are written and `launchctl load` returns 0.

### B.2 Plist sanity

```sh
ls -la ~/Library/LaunchAgents/com.hermes.{telegram-bot,backup}.plist
launchctl list | grep hermes
```

Both files exist at mode `0600`. `launchctl list` shows both labels (PID
column non-`-` for `telegram-bot`; `-` is normal for the periodic `backup`).

### B.3 Telegram bot is reachable

```sh
~/.local/pipx/venvs/hermes/bin/python -c \
  "import urllib.request, json, os; \
   tok = open(os.path.expanduser('~/hermes_config/secrets.env')).read().split('TELEGRAM_BOT_TOKEN=')[1].split('\n')[0]; \
   print(json.load(urllib.request.urlopen(f'https://api.telegram.org/bot{tok}/getMe', timeout=15))['result']['username'])"
```

Expected: prints the bot username (e.g. `hermes_ai_best_bot`).

### B.4 Backup round-trip

```sh
brew install restic                       # if not already
sleep 60                                  # let the next scheduled tick fire,
launchctl kickstart -k "gui/$(id -u)/com.hermes.backup"   # or kick it immediately
tail -20 ~/Library/Logs/hermes-backup.out.log
set -a; . ~/hermes_config/secrets.env; set +a
restic -r ~/backups snapshots | tail -10
restic -r ~/backups check
```

Expected: a fresh snapshot row + `restic check` says `no errors were found`.

### B.5 Final verify

```sh
hermes verify
```

Expected: all `match` (or only `brew-deps … missing` for any plugin whose deps
the VM still lacks).

✅ **Gate B passes** when the bot answers `getMe`, a fresh backup snapshot
exists, and `hermes verify` is clean.

---

## Failure triage

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `install aborted: no manifest at …` | Tool repo has no `manifest/hermes.yaml` | Pull latest `main` of `hermes_setup` (post-`075ddcf`) |
| `hermes-*` not found after install | `pipx inject` didn't use `--include-apps` | Pull latest installer; re-run `hermes install` |
| Scheduled backup logs `restic not found` | launchd PATH missing `/opt/homebrew/bin` | Pull latest installer (`step_launchd_jobs` injects `PATH`) |
| Telegram worker silent + no PID in `launchctl list` | Bad token / chat IDs | Validate `TELEGRAM_BOT_TOKEN` (must be `<digits>:<35+ chars>`) and `TELEGRAM_ALLOWED_CHAT_IDS` (numeric) |
| Permission prompts open System Settings to wrong pane | Stale TCC binding to old terminal | Quit Terminal completely, reopen, re-run `hermes doctor --fix` |

---

## Cleanup (optional)

```sh
launchctl unload ~/Library/LaunchAgents/com.hermes.*.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/com.hermes.*.plist
pipx uninstall hermes
rm -rf ~/.hermes_setup ~/.hermes ~/hermes_config ~/backups
```

(Doesn't revoke macOS TCC grants — those live in the system TCC DB and stick
to the terminal app's bundle id.)
