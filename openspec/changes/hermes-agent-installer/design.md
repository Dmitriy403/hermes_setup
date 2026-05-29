## Context

The Hermes agent — the user's curated Claude Code environment — currently lives implicitly in `~/.claude/` on a single MacBook. Its state is the sum of: the `claude` CLI version, ~30 personal/global skills, a handful of plugins, several MCP servers (gitcode, MemPalace, Gmail/Calendar/Drive OAuth), settings.json, hooks, custom commands, keybindings, and a CLAUDE.md with cross-project conventions. Re-creating this on a new machine is currently a multi-hour manual process. The `hermes_setup` repo is the home for an installer that turns this implicit state into a versioned, declarative manifest plus tooling to capture, install, and verify it. The repo is currently empty save for OpenSpec scaffolding and Claude skill commands.

Target users are: (1) the user himself, restoring or migrating his setup; (2) potentially teammates wanting to bootstrap the same baseline. Primary platform is macOS (Apple Silicon); Linux SHOULD work but is a secondary target. Windows is out of scope.

## Goals / Non-Goals

**Goals:**
- One repo that fully describes a Claude Code environment in human-readable, source-controlled form.
- `hermes capture` / `hermes install` / `hermes verify` round-trips losslessly for everything the manifest covers.
- Bootstrap from a fresh macOS install with a single `curl | sh`.
- Never commit secrets — secrets stay in a gitignored `secrets.env` and are referenced by env-var name in the manifest.
- Be safe to run multiple times (idempotent).

**Non-Goals:**
- Capturing conversation history, sessions, telemetry, or any per-project state under `~/.claude/projects/`.
- Managing macOS system state outside `~/.claude/` (Homebrew packages, dotfiles, shell config, etc.). Out of scope; users can layer their own dotfile manager.
- Cross-version Claude Code upgrades / downgrades. The manifest pins one version; switching versions is the user's job.
- A GUI. CLI only.
- Sandbox/VM-based reproduction. The installer mutates the real `~/.claude/` on the target machine.

## Decisions

### Decision 1: Implementation language — Python 3.11+ (stdlib + `pyyaml`)

Alternatives considered:
- **Pure Bash**: rejected. Manifest manipulation, YAML diffing, JSON merging, and cross-platform path logic are painful in shell. Maintainability cost too high.
- **Go**: rejected. Static binary is attractive, but adds a build step and toolchain that complicates `curl | sh` bootstrap and makes the codebase less hackable by the user (who lives in Python more than Go in adjacent projects).
- **Node**: rejected. Adds an `npm` toolchain dependency that we'd otherwise not need (the `claude` CLI is the only Node thing on the box for the same role).

Python wins because: stdlib covers everything except YAML; `pyyaml` is ubiquitous; the user already has Python via macOS / homebrew; the code stays inspectable. The bootstrap script will install Python via Homebrew if missing.

### Decision 2: Manifest layout — one root YAML + per-component sidecar files

```
manifest/
  hermes.yaml              # top-level index + version pins + small inline values
  CLAUDE.md                # verbatim copy of ~/.claude/CLAUDE.md
  settings.json            # redacted copy of ~/.claude/settings.json
  keybindings.json         # verbatim, if present
  skills/<name>/           # per-skill: source pointer + (for local skills) copy of the skill dir
  plugins.yaml             # list of {name, marketplace, version}
  mcp/<name>.yaml          # per-MCP-server: command, args, env (with ${VAR} placeholders)
  commands/                # verbatim copies of ~/.claude/commands/
  hooks/                   # any scripts referenced from settings.json
secrets.env.example        # generated alongside the manifest; lists required env vars
secrets.env                # gitignored; user-supplied
```

Alternatives:
- **Single monolithic YAML**: rejected. CLAUDE.md and settings.json are too big and too edit-prone to live inline.
- **Per-component repos / submodules**: over-engineered for v1.

The split keeps diffs reviewable and lets the user hand-edit individual components without parsing a giant file.

### Decision 3: Skill sources — three kinds (`local`, `git`, `marketplace`)

A skill entry in `manifest/skills/<name>/skill.yaml` has a `source` field of:
- `local`: a copy of the skill directory lives at `manifest/skills/<name>/files/`. Install copies it back into place.
- `git`: a `{repo, ref}` pair. Install runs `git clone --depth 1 --branch <ref>`.
- `marketplace`: a `{marketplace, name, version}` triple. Install delegates to `claude` CLI's plugin install.

Capture defaults to `local` for user-authored skills and to `marketplace`/`git` when the origin can be inferred.

### Decision 4: Secret detection — pattern-based with explicit allowlist

We will ship a default regex set (matches `sk-…`, `ghp_…`, OAuth refresh tokens, `*_KEY|*_TOKEN|*_SECRET` field names with high-entropy values) and an `manifest/.redact.yaml` file the user can edit to add patterns. On every capture, any matched value is replaced with `${VAR}` and `VAR` added to `secrets.env.example`. The user reviews the diff before committing — defense in depth.

Alternative (rejected): require user to mark secret fields manually. Too easy to forget; one leaked key is worse than a few false-positive `${VAR}` placeholders.

### Decision 5: Install ordering & atomicity

Install steps run in this order so each can depend on the previous:
1. Validate manifest schema and resolve all `${VAR}` references → abort early on missing secrets.
2. Install `claude` CLI at the pinned version (if not already at that version).
3. Write `CLAUDE.md`, `settings.json`, `keybindings.json` to a staging directory.
4. Install skills (local copy, git clone, or `claude plugin install`).
5. Install plugins.
6. Register MCP servers via `claude mcp add` (or by writing settings.json — TBD, see Open Questions).
7. Write custom commands and hooks.
8. Atomically move staged files into `~/.claude/`.

If any step fails, previously-written files remain (we don't try to roll back), but the failure message tells the user what to fix and `hermes install` can be re-run safely.

### Decision 6: Verification — content hashes for files, structural compare for structured data

For each manifest entry, verify computes:
- For verbatim files (CLAUDE.md, keybindings.json, command scripts): SHA-256 of expected vs. actual content.
- For `settings.json` and other structured JSON: parse both, diff the structures (ignoring key order), and ignore fields explicitly listed as "user-local" (e.g., recent-projects lists).
- For skills installed from git: check the on-disk HEAD hash matches `ref`.
- For marketplace plugins: check the installed version matches the pin.

### Decision 7: Repo distribution & bootstrap URL

The repo is hosted on the user's preferred forge (GitHub or gitcode — TBD). `install.sh` is parameterized so the URL is the only thing to swap. Bootstrap flow:

```sh
curl -fsSL https://<host>/<user>/hermes_setup/raw/main/install.sh | sh
```

`install.sh` is responsible for: detecting OS, installing Homebrew if missing (macOS), `brew install python git node`, `npm i -g @anthropic-ai/claude-code` at the pinned version (or whatever the official install command is at that time), cloning the repo to `~/.hermes_setup`, and `exec`ing `python3 -m hermes install`.

## Risks / Trade-offs

- **Risk**: Secret detection misses a non-standard key shape → secret leaks into the manifest.
  **Mitigation**: capture prints a summary of redactions performed and warns "review the diff before committing". Document the `.redact.yaml` extensibility. Add a pre-commit hook (separate task) that scans staged files for high-entropy strings.

- **Risk**: Claude Code's internal file layout under `~/.claude/` changes between versions, breaking capture/install.
  **Mitigation**: pin `claude` CLI version in the manifest; treat `~/.claude/` layout as a versioned contract; bump `schema_version` when adapting to a new layout.

- **Risk**: MCP server registration mechanism is unstable (settings.json edits vs. `claude mcp add` CLI).
  **Mitigation**: prefer the `claude mcp` CLI when available; fall back to settings.json edits gated by version detection. Documented in code with a comment pointing at this design doc.

- **Risk**: Marketplace plugins on a new machine require interactive OAuth (Gmail, Calendar, Drive) that the installer can't replay.
  **Mitigation**: the manifest captures the *registration*, not the OAuth tokens. After install, the user runs `claude` and authenticates each MCP server interactively. `hermes verify` does not flag missing OAuth tokens — only missing registrations.

- **Trade-off**: Idempotency vs. user edits. If the user hand-edits a managed file between installs (e.g., adds a setting to `settings.json` they forgot to capture), the next `hermes install` will overwrite their change. `hermes verify` exists specifically so the user can catch this drift before it gets clobbered. Documented in README.

- **Trade-off**: macOS-first. Linux support is best-effort. We accept that some paths (e.g., Homebrew install) won't work on Linux and the bootstrap script will branch on `uname`. Windows users are explicitly told to use WSL.

## Migration Plan

This is a greenfield project, so there is no migration. The rollout for the *user* is:
1. Build the installer in this repo.
2. Run `hermes capture` against the user's current machine — this is the moment-of-truth seed of the manifest.
3. Review the resulting diff (especially for missed secrets) before committing.
4. Test `hermes install` against a clean VM (Multipass or UTM) and confirm `hermes verify` returns clean.
5. Document the bootstrap URL and add it to `~/.claude/CLAUDE.md` so future-self can find it.

Rollback: delete `~/.hermes_setup` and `~/.claude/`; restore from a Time Machine backup. No system-wide state is touched outside those two paths.

### Decision 8: Bundled plugins are MCP servers in this same repo

The five required plugins (Telegram bot, vision, macOS control, voice, backups) live under `plugins/<name>/` in this repo, not in separate repos or marketplaces. Rationale:
- They are tightly coupled to the user's specific setup (his Telegram bot token, his macOS, his backup destinations) and not generally distributable.
- Keeping them in-tree means the manifest can reference them by relative path and the bootstrap script doesn't need extra clones.
- The `manifest` capability still supports git/marketplace skills for everything else.

Each plugin is its own Python package with a `pyproject.toml`; the top-level `pyproject.toml` declares them as path dependencies. The manifest's `manifest/mcp/*.yaml` entries reference these local packages as their `command`.

### Decision 9: Vision is a skill, not an MCP server

`plugin-vision` is implemented as a Claude Code *skill* (markdown + minimal helper script), not an MCP server. Rationale: vision is just "send the image to Claude and ask"; an MCP server would add latency and code with no benefit. A skill packages the prompt patterns (describe/ocr/extract modes) and is invoked directly by Claude.

Alternatives considered: a dedicated MCP server. Rejected because it would just wrap the same Claude API call and add a process boundary.

### Decision 10: Telegram bot architecture — long-poll, single process

The `telegram-bot` MCP server runs a long-polling worker (no webhook, no public-IP requirement) using `python-telegram-bot`. It maintains an in-memory ring buffer of the last N messages from allowlisted chats so MCP tools (`tg_get_latest_messages`, `tg_get_voice`, etc.) can serve recent traffic without re-fetching from Telegram.

Alternatives:
- **Webhook**: rejected. Requires HTTPS endpoint / tunnel, more moving parts.
- **One process per call**: rejected. Telegram rate-limits and reconnect cost would be painful.

Process supervision: run under `launchd` (`com.hermes.telegram-bot.plist`) so it restarts on crash and on login.

### Decision 11: Voice — bundled whisper.cpp default

`plugins/voice/` ships with a `vendor/whisper.cpp` git submodule (or a `brew install whisper-cpp` dependency, TBD in tasks) and a small Python wrapper. Model files are downloaded on first use to `~/.cache/hermes/whisper/` (not committed). Default model `base` (~140MB) is a balance of speed and quality for short voice notes; user can switch via env var.

Cloud fallback (OpenAI Whisper API) is off by default and gated by `VOICE_CLOUD_MODE` to keep the privacy story default-on (no audio leaves the machine).

### Decision 12: Backups — restic + launchd, not Time Machine

restic was chosen over Time Machine because:
- It is selective (we want to back up a specific list of paths, not everything).
- It supports diverse destinations (local disk, external, rclone-backed cloud).
- It is scriptable and verifiable (`restic check`).
- Time Machine is opaque, all-or-nothing, and tied to macOS.

Scheduling is via `launchd` (not cron) because launchd is the macOS-native mechanism, wakes the machine, and survives reboots. Default schedule: hourly incremental, daily full check, weekly verify.

### Decision 13: Plugin permissions are documented, not auto-granted

`macos-control` requires Accessibility and Screen Recording permissions. Granting these via script is intentionally not done — it would require disabling SIP or using TCC-bypass tricks, which we reject on security grounds. The installer prints a checklist with exact System Settings paths and pauses for the user to confirm.

### Decision 14: Security model is layered (visibility + enforcement + optional sandbox)

The Hermes security surface is not just a `permissions.allow` list copied from `~/.claude/settings.json`. It is a declarative manifest with three execution layers, only the first two of which are mandatory in v1:

- **Layer A — `permissions.yaml` + `PreToolUse` hook (always active).** A single declarative file under `manifest/permissions.yaml` lists every capability the agent is allowed to use: filesystem paths (write-exec / write / read / forbidden), shell commands (allow / ask / deny), network domains, MCP tools, and TCC categories with the bundle ids and paths each plugin needs. `hermes install` translates the policy into a `PreToolUse` hook that blocks disallowed `Write`, `Bash`, `WebFetch`, and MCP tool calls before they reach the OS. This works on every OS and does not depend on macOS-specific sandbox plumbing.
- **Layer B — `sandbox-exec` profile (opt-in).** When the user opts in via `permissions.yaml: security.layer_b.enabled: true`, `hermes install` generates `~/.hermes/profile.sb` from the same `permissions.yaml` and `hermes run` starts Claude under `sandbox-exec -f ~/.hermes/profile.sb`. The profile is a *derived artifact*, not a source-of-truth — it lives in the runtime directory (mirroring how `settings.json` is derived from the manifest), is regenerated by every install, and is never committed to the repo. Seatbelt provides kernel-level filesystem and Apple-Events enforcement; network filtering remains coarse (port-level only — domain rules stay with Layer A). Because Seatbelt-blocked API calls return errors that are indistinguishable from TCC-denied calls at the return-value level (Apple designed it this way for secure-by-default UX), debugging Layer B without help is opaque. The `doctor` capability handles this by running a *differential probe* — one pass without the sandbox and one pass through `sandbox-exec -f ~/.hermes/profile.sb hermes-probe-tcc --self-test` — and classifying each TCC category along a 2×2 matrix (TCC granted? × Sandbox allows?). The `SANDBOX_BLOCKED` cell, plus a "profile gap report" that names the missing `allow` rules per blocked category, is what makes Layer B usable in practice; the alternative is mysterious silent failures. Layer B is **not enabled by default** in v1.
- **Layer C — VM mode (paranoid, deferred).** A `hermes vm-mode` that launches Claude inside a Lima or tart VM with only `~/projects/` mounted is explicitly out of scope for v1 and recorded as a future extension.

Alternatives considered:
- **Policy lives only in `~/.claude/settings.json`'s `permissions.allow`.** Rejected. The native field is a flat list of patterns; it cannot express filesystem path classes (write-exec vs read), per-plugin TCC declarations, or domain-aware network rules. Keeping policy in `manifest/permissions.yaml` allows the same source to drive the hook, the sandbox profile, the doctor, and `hermes capabilities`.
- **Endpoint Security framework client.** Rejected. Requires a paid Apple Developer ID, notarization, and a kernel-extension-class signing entitlement that is unrealistic for v1.
- **Running Claude as a dedicated `_hermes` POSIX user.** Rejected for v1. Strong isolation, but breaks keychain access, TCC attribution to the user's terminal, and Telegram-bot launchd integration. May revisit as an opt-in mode.

The current `~/.claude/settings.json` captured from the user's machine grants `Bash(*)`, `Edit(*)`, `Write(*)`, `Read(*)` — i.e., no boundary. Layer A is the first real boundary the project introduces.

### Decision 15: `hermes doctor` is the TCC-checkup subsystem

`hermes doctor` is a separate capability (`specs/doctor/`) that probes macOS TCC permissions silently and reports whether each required category is granted to the correct responsible process. Rationale:
- TCC binds permissions to a *responsible process* (typically the host terminal), not to the `claude` binary. When the user switches terminals (Ghostty → iTerm → VS Code), TCC silently revokes access and macOS APIs start returning misleading errors. Without a checkup, this is hours of mystery debugging.
- TCC permissions cannot be granted from scripts; they require System Settings GUI or an MDM `PPPC` profile. Doctor compensates by detecting state precisely and emitting deep-link URLs (`x-apple.systempreferences:com.apple.preference.security?...`) so the user is one click away from the right pane.
- `hermes doctor` is read-only by default. The `--fix`, `--warmup`, and `--reset` modes exist as separate verbs so automated contexts (CI, hooks) never accidentally trigger TCC prompts.

Doctor relies on a separate probe binary `bin/hermes-probe-tcc` (Decision 16) and maintains a per-user cache at `~/.hermes/probe-cache.json` (Decision 17). It classifies state along three axes — cdhash mismatch, responsible-bundle mismatch, and pure TCC revoke — so the user understands *why* a permission was lost (probe was rebuilt vs terminal was swapped vs TCC was reset).

Alternative (rejected): bundle the probe logic into the Python `hermes` CLI via `pyobjc`. This works in principle but ties the probe's TCC identity to the system Python interpreter, making cdhash detection effectively useless and bloating bootstrap. The separation of `doctor` (Python) from `probe-tcc` (Swift Mach-O) is intentional.

`hermes doctor` MUST NOT auto-register as a Claude `SessionStart` hook. Probing adds 200–500 ms to every Claude startup, which is unacceptable as a default cost. Opt-in is via a manifest field `hooks.doctor_on_session_start: true` that `hermes install` translates into the appropriate hook entry.

### Decision 16: Probe binary signing — ad-hoc (Scenario A) for v1

The probe binary `bin/hermes-probe-tcc` is signed ad-hoc (`codesign --sign -`) with `--identifier org.hermes.probe-tcc`. No Apple Developer account is required, no annual fee, no payment rail.

Trade-off accepted: TCC for ad-hoc binaries uses a *literal cdhash* designated requirement. Any rebuild of the probe produces a new cdhash, which TCC treats as a new application, and all granted permissions must be re-issued. `hermes doctor` detects this automatically (Decision 15) and displays a clear "re-grant" instruction with deep-links, so the friction is bounded.

Alternatives considered:
- **Apple Developer Program ($99/year) with `Developer ID Application` cert + `notarytool`.** This would give a stable designated requirement (`identifier == ... and anchor apple generic and certificate leaf ...`), so the same identifier across rebuilds would preserve TCC grants. Rejected for v1: the program requires a payment rail that is not currently available to the maintainer through ordinary means since spring 2022 (Apple Pay and Russian cards are not accepted; foreign-issued cards or a foreign legal entity are required). When that channel becomes available, migration is a single environment-variable change in `build.sh` (`IDENTITY=ad-hoc | <Developer ID>`).
- **Free Apple Developer account (Xcode TOS only, no $99).** Rejected. This produces an `Apple Development` cert valid only on the developer's own machines and does not enable `notarytool`. Each end user would have their own cert, so the cdhash-stability property is not actually obtained — the friction is the same as ad-hoc plus configuration overhead.
- **Self-signed certificate via a local keychain identity.** Rejected. Same cdhash-stability problem as ad-hoc, with extra setup steps and a confusing trust story for end users.

The signing strategy is captured in `specs/probe-tcc/`. Migration to a paid-program identity is a future scope.

### Decision 17: `~/.hermes/` is the runtime directory for Hermes

Hermes writes runtime state under `~/.hermes/`, an analog of `~/.claude/`. v1 contents:
- `~/.hermes/probe-cache.json` — Doctor's per-user cache (cdhash, grants, history).
- `~/.hermes/logs/` — reserved for future audit logs from Layer A hook.
- `~/.hermes/profile.sb` — generated Seatbelt profile when Layer B is opted in.

`~/.hermes/` MUST be created with mode `0700` and individual files with `0600`. If `~/` is read-only (rare; some sandbox-style setups), Hermes falls back to `~/Library/Application Support/Hermes/` and logs a warning.

Alternatives considered:
- **Reuse `~/.hermes_setup/`** — the repo clone path. Rejected. That directory holds source code under version control; mixing runtime state into it would create confusing diffs and complicate `git clean`.
- **`~/.config/hermes/` + `~/.cache/hermes/` (XDG).** Considered. macOS has weak XDG support and most Hermes-adjacent tooling (Homebrew, `~/.claude/`) lives under `~/.<name>/`. Consistency with that pattern wins for v1.

### Decision 18: Plugin external dependencies — fail-soft + lazy install

The bundled plugins depend on external binaries that are **not** present by default (verified 2026-05-28 on the maintainer's machine: `restic`, `rclone`, `whisper-cpp`, `ffmpeg` all absent; only `osascript`/`screencapture` ship with macOS). Two conventions follow:

**A. Missing-dependency errors are structured, never raw exceptions.** When a plugin tool is invoked but its external binary is absent, the tool MUST return the same shape used for TCC failures in `macos-control`:

```json
{"ok": false, "error": "missing_dependency",
 "needs": "whisper-cpp",
 "how_to_fix": "brew install whisper-cpp"}
```

Detection is a `shutil.which(...)` check at the call boundary — cheap and unit-testable by mocking `which` to return `None`. This keeps the failure legible to Claude (which can relay the install command to the operator) instead of surfacing a `FileNotFoundError`.

**B. Heavy dependencies install lazily, not at bootstrap.** `install.sh` and `hermes install` install only the *core* prerequisites (`python`, `git`, `node`, `pipx`, the `claude` CLI). Plugin-specific binaries (`restic`, `rclone`, `whisper-cpp`, `ffmpeg`) are **not** installed eagerly — the bootstrap stays lean and the user does not pay whisper's ~140 MB model download or a restic install unless they actually use voice/backups. The first use of a plugin whose binary is missing fails-soft per (A) with the `brew install` hint.

To make missing deps discoverable in one place, `hermes doctor` SHALL grow an optional "plugin dependencies" section that runs the same `which` checks across all registered plugins and lists every missing binary with its install command. This is reporting only — doctor never installs anything (symmetric with its TCC stance).

Alternatives considered:
- **Eager install at bootstrap** (`brew install restic rclone whisper-cpp ffmpeg` in `install.sh`). Rejected for v1: heavy first-run cost for capabilities the user may never invoke; couples bootstrap success to Homebrew formula availability for four extra packages.
- **Per-plugin `pyproject` declaring the binaries.** Not possible — these are system binaries, not Python packages; `pip`/`pipx` can't install them.

Consequence for testing: the live edge of `voice`/`backups`/`telegram-bot` (real whisper/restic/Telegram round-trips) is **not** exercisable in CI on a machine without the deps. The pure cores (argv construction, exclude lists, backend selection, allowlist, ring buffer, output parsing, plist generation) are fully unit-tested; the live round-trips are deferred to the §6.5 VM test / real-machine smoke, documented per plugin.

### Decision 19: Scope split — ship v0.1.0 (installer + security + 2 plugins), defer 3 plugins to a follow-on

This change carries two separable theses: **(A)** "a portable, secure Claude Code environment" (capture/install/verify + the four-layer security model + bootstrap, plus `vision` and `macos-control` which prove the skill and MCP-server install paths), and **(B)** "five bundled agent capabilities." Thesis A is the novel, hard, fully-tested work; thesis B's remaining three plugins (`telegram-bot`, `voice`, `backups`) are "more plugins" that add no new install mechanics.

**Decision (2026-05-28): ship A + the two built plugins as v0.1.0 and move `telegram-bot` / `voice` / `backups` to a follow-on change `hermes-bundled-agent-plugins` (v0.2.0).**

Rationale:
- The seam that matters is **verifiability on this machine**, and it falls cleanly between the two done plugins (fully tested) and the three remaining (live edges untestable here — restic/rclone/whisper-cpp/ffmpeg all absent; Telegram needs a live token). Letting untestable-here work block the tested, novel core from shipping is the wrong trade.
- The three deferred plugins are forward-looking *additions* to the agent, not part of making the *existing* environment portable. Proof: `hermes capture` of the real `~/.claude` (§12) contains none of them — they don't exist on the machine yet.
- v0.1.0 tells a clean story: "make my existing setup portable, secure, and backed-up-as-a-repo." v0.2.0 grows the agent: remote control (telegram), transcription (voice), scheduled restic backups.

Alternatives considered:
- **Finish all five here.** Rejected — keeps the biggest change open longest and gates a tested v0.1.0 behind three plugins that can't be verified in this environment.
- **Keep `backups` in v0.1.0** (thematically it's the "recoverable" keystone). Rejected — `backups` is *also* untestable here (no restic), so it sits on the wrong side of the verifiability seam; the thematic tidiness isn't worth muddying the seam.

**Pre-archive obligation:** before archiving this change, the three deferred spec directories (`specs/plugin-telegram-bot/`, `specs/plugin-voice/`, `specs/plugin-backups/`) MUST be moved into the follow-on change, and task sections §7/§10/§11 with them. Otherwise `openspec archive` would promote those specs to `openspec/specs/` as if implemented. The follow-on change inherits the already-written specs and tasks unchanged; Decision 18 (fail-soft + lazy deps) governs its implementation.

### Decision 20: Two-repo architecture — public tool, private config

`hermes_setup` is a **public** repo on gitcode. The captured personal manifest (CLAUDE.md, settings.json, the user's authored skills) contains no credentials, but it does expose the user's macOS username, project names, and private workflow. The decision (2026-05-28) is to keep two repos:

- **`hermes_setup` (public)** — the reusable TOOL: the `hermes` CLI, the four-layer security framework, the bundled plugins (`vision`, `macos-control`), the probe binary, `install.sh`, and a `manifest/` holding only **factory defaults** (the starter `permissions.yaml`, `probe-tcc.yaml`, and the bundled-plugin entries `skills/vision/` + `mcp/macos-control.yaml`). Nothing personal.
- **`hermes_config` (private)** — the user's captured manifest: their `CLAUDE.md`, `settings.json`, personal skills (`gitcode-pr-*`, `review-*`), `plugins.yaml`, `mcp/`, `commands/`, `hooks/`, and a gitignored `secrets.env`. This is the real backup/portability artifact.

This requires **decoupling two notions that are currently both `repo_root()`**:

```
   tool_root()    → bin/hermes-probe-tcc, tools/probe-tcc/sandbox-rules.yaml,
                    the installed `hermes` package. Fixed at the tool's location.
   manifest_dir() → the capture/install/verify target. Resolved from
                    --manifest-dir <path>  or  HERMES_MANIFEST_DIR env,
                    defaulting to tool_root()/manifest (the factory defaults).
```

So `hermes capture --manifest-dir ~/hermes_config` writes the personal manifest into the private repo; `hermes install --manifest-dir ~/hermes_config` reproduces it; the public repo is never touched by capture. Out-of-the-box (`hermes install` with no flag) installs the factory defaults + bundled plugins from the tool's own `manifest/`.

**`$HOME` path templating (capture/install).** Capture MUST rewrite the current user's `$HOME` prefix to `${HOME}` in **structured** files — `settings.json` values, MCP server `env`/`command`, and hook command strings — and install MUST expand `${HOME}` back to the target machine's home. This fixes a real portability bug (a verbatim `/Users/dtrubenkov/...` hook path is broken on any machine with a different username — which defeats the installer's core promise) and, as a bonus, scrubs the username from the (even-private) config repo. CLAUDE.md is left verbatim (it is the user's prose; rewriting paths inside it risks changing meaning — the user edits it by hand if desired). Only the *current* `$HOME` prefix is rewritten; other absolute paths (`/opt/homebrew`, `/usr`) are left alone.

Alternatives considered:
- **Single public repo with config committed.** Rejected — publishes the user's personal config (username, workflow, project names) to a world-readable, indexable repo. No credentials would leak, but the exposure is unnecessary when a clean tool/config split is cheap.
- **Single repo, config gitignored, backup via restic only.** Considered (shape 2). Reasonable, but loses git versioning/history of the config and couples "do I have a backup" to restic being set up. The private repo gives versioned config history for free.

Consequence for §12: "seed the real manifest" now means `hermes capture --manifest-dir ~/hermes_config` into the **private** repo, then commit there — NOT into this public repo, which stays tool-only. New v0.1.0 plumbing tasks (§18) implement the `tool_root`/`manifest_dir` split and `$HOME` templating.

## Open Questions

1. **Repo host** — GitHub vs. gitcode? The user already uses gitcode for some projects; bootstrap URL needs to be picked before `install.sh` can be written. **Resolved (2026-05-27): gitcode** — the user's primary forge (per their cross-project conventions). The `install.sh` bootstrap URL is parameterized (Decision 7), so this can be re-pointed cheaply if it changes before the bootstrap task lands.
2. **MCP registration mechanism** — `claude mcp add` CLI vs. direct settings.json edits. Needs a quick spike against the current CLI version (1.x) to confirm CLI coverage. **Resolved (2026-05-28, v1): direct settings.json `mcpServers` edits.** `hermes install` writes resolved MCP server defs into `~/.claude/settings.json`'s `mcpServers` map. Rationale: deterministic, testable without a live `claude` binary, and idempotent. Note: on this machine global settings.json has no MCP servers (the mempalace MCP rides its plugin), so this path is exercised mainly by captured/authored servers. Revisit `claude mcp add` if a future CLI version makes settings.json edits unreliable.
3. **CLI binary name conflict** — is `hermes` already taken by some other tool the user might want? Fallback: `hermes-agent` or `hermes-setup`. **Resolved (2026-05-27): `hermes`** — verified no conflicting binary on the user's PATH (`type -a hermes` shows only the pipx-installed entrypoint). `pyproject.toml` ships the `hermes` console-script.
4. **Selective install** — do we need `hermes install --only skills,mcp` symmetric to `capture --only`? Probably yes for iteration, but tasks.md leaves it as a stretch goal.
5. **Versioning the manifest itself** — should `manifest/hermes.yaml` carry a `manifest_version` independent of `schema_version`, so we can detect "this manifest was last captured at v1.4 but the CLI is v1.5"? Leaning yes; deferring decision until first real schema change.
6. **Whisper bundling** — bundle `whisper.cpp` as a git submodule (heavy clone, reproducible) or depend on `brew install whisper-cpp` (lighter, depends on Homebrew formula stability)? Defaulting to brew for v1, may revisit if the formula disappears.
7. **Telegram conversational loop** — should the bot wake Claude on every incoming message (proactive agent loop) or only serve as a tool when Claude is already running? v1: passive tool only. Proactive mode is a follow-on change.
8. **Backup destination defaults** — should we ship a default `manifest/backups.yaml` pointing at `/Volumes/HermesBackup/` (external disk) or leave the destination unset and force the user to configure on first install? Leaning unset to avoid silently writing to a wrong path.
9. **Restic repo init** — should `hermes install` `restic init` a new repo automatically the first time, or require the user to do it? Auto-init risks creating an empty repo at the wrong destination; manual is safer but adds a step. Defaulting to manual with a clear error message.
10. **`permissions.yaml` defaults.** **Resolved (2026-05-26).** v1 ships an opinionated "unlocked profile" — allow-by-default plus a targeted denylist. Rationale: the existing user has `Bash(*)/Edit(*)/Write(*)/Read(*)` and switching to deny-by-default in v1 = two changes (visibility + tightening) at once, which is painful and obscures whether failures come from the new model or from a too-narrow allowlist. The starter file's job is to demonstrate the schema concretely, add a meaningful denylist (ssh keys, `.env`, keychains, TCC.db), and prove the Layer A hook fires. A stricter `tighten-permissions` change (deny-by-default + per-project overlay) is a planned follow-on.

  Sub-decisions baked into the starter:
  - **`network.default: ask`** — neither broad-allow nor deny-by-default. Unlisted domains trigger Claude's native permission prompt. Avoids constant breakage from `brew`/`pip` mirror domains while still surfacing the network surface.
  - **`shell.deny`** includes `osascript` even though some workflows use it interactively — the manifest expects callers to use the `macos-control` MCP server. Same logic applies to `tccutil` (use `hermes doctor --reset`) and `defaults`/`launchctl` (no agent has a legitimate reason to touch these).
  - **`shell.ask`** entries (`curl`, `wget`, `ssh`, `scp`, `rsync`, `rm`) are checked at the command-name level only — no arg-pattern matching in v1. Patterns like `rm -rf /` are caught by the absolute denylist in `shell.deny`.
  - **`hermes capture` round-trip = option C (starter + machine overlay).** Capture starts from the shipped starter, then enriches: adds discovered MCP servers to `mcp.enabled`, adds any `WebFetch(domain:...)` entries from the live `~/.claude/settings.json` to `network.domains`, leaves everything else identical to the starter. This means upgrading an existing setup gets the denylist for free without losing tool-level allowances the user already configured.

  See the full starter content in `Appendix A: starter permissions.yaml` below.
11. **Layer B network filtering** — Seatbelt cannot express domain-based network rules. If the user opts into Layer B and also wants `WebFetch(domain:gitcode.com)` style restrictions, the rules live in the Layer A `PreToolUse` hook only; the sandbox profile expresses port-level rules. **Resolved (2026-05-26)**: documented in `specs/manifest/spec.md` under "Network filtering granularity is documented". `hermes doctor --suggest-sandbox-patch` deliberately does not include domain rules in its diff output; domain filtering remains a Layer A concern.
12. **MDM PPPC profile coverage** — Apple does not document which TCC categories are grantable via PPPC payloads, and the list shifts between macOS versions. `hermes doctor --mdm-profile` for v1 emits categories that are widely supported (Accessibility, Automation, Files & Folders) and explicitly excludes Screen Recording and Full Disk Access. Revisit when targeting macOS 26+.

## Appendix A: starter `manifest/permissions.yaml`

This is the file `hermes install` lays down on first run when no `manifest/permissions.yaml` exists yet. `hermes capture` round-trip starts from this content and overlays machine-discovered MCP servers and `WebFetch` domains (see Decision-resolved Q10 above).

```yaml
# manifest/permissions.yaml
#
# UNLOCKED PROFILE — broad allow + targeted denylist.
# v1 default: does NOT break a typical Claude Code workflow but DOES
# add explicit forbidden paths and shell deny rules that catch common
# foot-guns. For tighter posture see the planned `tighten-permissions`
# change (deny-by-default + per-project overlay).

schema_version: 1

filesystem:
  # Claude can read, write, and execute from these paths.
  write-exec:
    - "~/projects/**"
    - "~/.hermes_setup/**"
    - "/tmp/**"

  # Claude can write here, but Bash will not cd here or run binaries
  # from these paths (defense-in-depth against dropped scripts).
  write:
    - "~/Documents/**"
    - "~/.claude/projects/**"
    - "~/.cache/**"
    - "~/.hermes/**"

  # Read-only zones.
  read:
    - "~/Desktop/**"
    - "~/Downloads/**"
    - "/usr/local/**"
    - "/opt/homebrew/**"
    - "~/Library/Application Support/Claude/**"

  # Hard deny — wins over any allow above.
  forbidden:
    - "~/.ssh/**"
    - "~/.aws/**"
    - "~/.gnupg/**"
    - "~/.config/gh/**"
    - "~/Library/Keychains/**"
    - "~/Library/Application Support/com.apple.TCC/**"
    - "~/Library/Cookies/**"
    - "**/secrets.env"
    - "**/.env"
    - "**/.env.local"
    - "**/credentials.json"
    - "**/id_rsa*"
    - "**/id_ed25519*"
    - "**/*.pem"
    - "**/*.key"

shell:
  # Allowed without prompt. Matches Bash(<cmd>) where <cmd>'s
  # leading token equals one of these.
  allow:
    - git
    - python3
    - pip
    - npm
    - node
    - brew
    - claude
    - gh
    - restic
    - rclone
    - ls
    - cat
    - grep
    - find
    - awk
    - sed
    - jq
    - openspec

  # Prompt the user before running (Claude's native permission UI).
  ask:
    - curl
    - wget
    - ssh
    - scp
    - rsync
    - rm

  # Hard deny — never run, no prompt.
  deny:
    - sudo
    - security             # macOS keychain CLI — only via plugins
    - osascript            # only via plugin-macos-control's MCP
    - defaults             # system-wide defaults writes
    - launchctl            # user/system agent manipulation
    - tccutil              # only via `hermes doctor --reset`
    - "rm -rf /"
    - "rm -rf ~"
    - "rm -rf ~/*"
    - "chmod -R 777"
    - "dd if=*of=/dev/*"

network:
  # Domains accessible without prompt via WebFetch and URL-taking MCP
  # tools. Everything else triggers `default` behaviour.
  domains:
    - api.anthropic.com
    - api.openai.com           # voice cloud fallback (opt-in)
    - api.telegram.org
    - gitcode.com
    - github.com
    - raw.githubusercontent.com
    - pypi.org
    - files.pythonhosted.org
    - registry.npmjs.org

  # `ask` is the v1 default — pip/brew often pull from mirror domains
  # we did not pre-list, and deny here causes constant breakage.
  # Switch to `deny` in the tighten-permissions follow-on.
  default: ask

mcp:
  enabled:
    - "mempalace.*"
    - "telegram-bot.*"
    - "macos-control.*"
    - "voice.*"
    - "vision.*"
    - "backups.*"
  disabled: []

tcc:
  screen-recording:
    required-by: [macos-control]
  accessibility:
    required-by: [macos-control]
  automation:
    targets:
      - bundle-id: com.apple.finder
        required-by: [macos-control]
        reason: window listing and focus
      - bundle-id: com.apple.systemevents
        required-by: [macos-control]
        reason: keystroke injection and window control
  microphone:
    required-by: [plugin-voice]
    reason: recording for whisper.cpp
  full-disk-access:
    required-by: [plugin-backups]
    reason: read ~/Library for backup
  files:
    - path: "~/Documents"
      required-by: [plugin-backups]
    - path: "~/Desktop"
      required-by: [plugin-backups]

security:
  layer_b:
    enabled: false             # opt-in, off by default in v1
    profile_path: "~/.hermes/profile.sb"
```
