## 1. Project scaffolding

- [x] 1.1 Pick repo host (GitHub vs. gitcode) and CLI binary name (`hermes` vs. `hermes-agent`); record the decision in `design.md` Open Questions. *(Resolved: gitcode + `hermes`; see design.md Open Questions 1 & 3.)*
- [x] 1.2 Add `pyproject.toml` for a Python 3.11+ package named `hermes`, with `pyyaml` as the only runtime dependency and a `hermes` console-script entrypoint pointing at `hermes.cli:main`.
- [x] 1.3 Create `src/hermes/` with `__init__.py`, `cli.py`, `manifest.py`, `capture.py`, `install.py`, `verify.py`, `redact.py`, `paths.py`. *(`install.py` superseded by the `src/hermes/install/` package — created in §17 for sandbox_profile.py. capture/verify/redact are purpose-stated placeholders pending §3/§5.)*
- [x] 1.4 Add a top-level `.gitignore` that excludes `secrets.env`, `__pycache__/`, `.venv/`, `.DS_Store`, and `~/.claude/`-style ephemeral paths if anyone symlinks them in.
- [x] 1.5 Add `README.md` with a one-paragraph project summary and a "how to bootstrap a new machine" section (placeholder URL).

## 2. Manifest schema & I/O

- [x] 2.1 Define the `schema_version: 1` shape in `src/hermes/manifest.py` as typed dataclasses (root manifest, skills, plugins, mcp servers, hooks, commands).
- [x] 2.2 Implement `Manifest.load(repo_root)` that reads `manifest/hermes.yaml` plus all sidecar files into the dataclass tree.
- [x] 2.3 Implement `Manifest.save(repo_root, manifest)` that writes the dataclass tree back out, deterministic key order, stable formatting (so re-capture diffs are minimal).
- [x] 2.4 Implement env-var resolution: replace `${VAR}` placeholders using `os.environ` then `secrets.env` if present; return a list of missing vars for the caller to handle.
- [x] 2.5 Unit tests: round-trip load → save → load is a fixed point; missing env vars are reported correctly; malformed manifest raises a clear error. *(tests/test_manifest.py — 9/9 passing, runnable via pytest or standalone.)*

## 3. Capture

- [x] 3.1 In `src/hermes/paths.py`, define the canonical list of source paths to read and the canonical list of excluded paths under `~/.claude/`.
- [x] 3.2 Implement `capture_claude_md()`, `capture_settings()`, `capture_keybindings()`, `capture_commands()` — straightforward copy with redaction applied to settings.
- [x] 3.3 Implement `capture_skills()` that walks `~/.claude/skills/`, classifies each as local / git / marketplace (heuristic: presence of `.git`, presence of marketplace metadata, fallback to local), and writes per-skill sidecar files.
- [x] 3.4 Implement `capture_plugins()` by reading `~/.claude/plugins/installed_plugins.json` and emitting `manifest/plugins.yaml`.
- [x] 3.5 Implement `capture_mcp()` by extracting MCP server entries from settings.json, redacting their `env` maps, and writing one file per server under `manifest/mcp/`.
- [x] 3.6 Implement `capture_hooks()` by scanning settings.json for hook script references and copying the referenced scripts into `manifest/hooks/`.
- [x] 3.7 Implement `redact.py`: default pattern set (sk-, ghp-, common API-key field-name heuristics) + optional `manifest/.redact.yaml` for extra patterns; returns the redacted value and the discovered env-var name.
- [x] 3.8 Wire `hermes capture` in `cli.py` with `--only`, `--skip`, `--dry-run` flags; default = all components.
- [x] 3.9 Generate `secrets.env.example` from the union of all `${VAR}` placeholders discovered during capture.
- [x] 3.10 Unit/integration test: synthesize a fake `~/.claude/` tree in a tmpdir, run capture, assert the manifest matches a golden fixture and contains no literal secrets.

## 4. Install

- [x] 4.1 Implement manifest validation step: schema check + resolve all `${VAR}` references → exit early on missing.
- [x] 4.2 Implement `claude` CLI version pin check + install/upgrade (call out to npm or whatever official install path is at the time).
- [x] 4.3 Implement staging-directory write of `CLAUDE.md`, `settings.json`, `keybindings.json`; atomic rename into `~/.claude/` on success.
- [x] 4.4 Implement skill install — three branches: local copy, `git clone --depth 1 --branch <ref>`, or `claude plugin install` for marketplace skills.
- [x] 4.5 Implement plugin install by replaying `manifest/plugins.yaml` against the `claude` plugin CLI.
- [x] 4.6 Implement MCP server registration. Spike `claude mcp add` first; if not available, fall back to writing settings.json entries. Document the chosen path.
- [x] 4.7 Implement custom commands and hooks install (copy `manifest/commands/` → `~/.claude/commands/`, `manifest/hooks/` → wherever settings.json references them).
- [x] 4.8 Implement `--dry-run`: same code path, but every filesystem-mutating action goes through a single helper that logs instead of writing.
- [x] 4.9 Idempotency check: every install step compares manifest-derived expected state to actual state before mutating; logs "unchanged" if equal.
- [x] 4.10 Wire `hermes install` in `cli.py`; integration test against a tmpdir fake-home with `HOME` override.

## 5. Verify

- [x] 5.1 Implement per-component verifiers that return a list of `{component, name, status, detail}` records where status ∈ {match, missing, extra, modified}.
- [x] 5.2 Implement settings.json structural diff that ignores key order and user-local fields.
- [x] 5.3 Implement git-skill HEAD hash check, marketplace-plugin version check, content-hash check for verbatim files.
- [x] 5.4 Implement human-readable report formatter (default) and `--json` formatter; non-zero exit code if any drift is found.
- [x] 5.5 Wire `hermes verify` in `cli.py`; integration test that capture → install → verify on a fresh fake-home reports zero drift.

## 6. Bootstrap

- [x] 6.1 Write `install.sh` at repo root: detect macOS vs. Linux, install Homebrew if missing (macOS), `brew install python git node`.
- [x] 6.2 In `install.sh`, install the `claude` CLI at the version pinned by the manifest (or latest if no manifest yet).
- [x] 6.3 In `install.sh`, clone the repo to `~/.hermes_setup` (or `git -C` pull if it already exists) and `pip install -e ~/.hermes_setup`.
- [x] 6.4 In `install.sh`, honor `HERMES_NONINTERACTIVE=1` and `HERMES_SECRETS_FILE=/path`; otherwise prompt the user to populate `secrets.env` before running `hermes install`.
- [ ] 6.5 End-to-end manual test on a clean macOS VM: `curl … | sh` → followed by `hermes verify` returns clean. *(MANUAL: runbook lives at [tools/vm-bootstrap-test.md](tools/vm-bootstrap-test.md) — Flow A covers zero-config; gates A.1–A.6 must pass. Cannot be automated; the automated pieces (pipx install, hermes install/verify, install.sh syntax+config-url flow) are covered by §1–§5 + §18 tests.)*

## 8. Plugin: vision (skill)

- [x] 8.1 Create `plugins/vision/SKILL.md` describing usage, supported `mode` values, and example invocations.
- [x] 8.2 Author prompt templates for `describe`, `ocr`, `extract` modes (each as a short Markdown section within the skill).
- [x] 8.3 Add a minimal Python helper `plugins/vision/run.py` that reads an image path, encodes to base64, builds the request body for the chosen mode, and shells out to `claude` (or uses the Anthropic SDK if already available locally).
- [x] 8.4 Manifest entry: register `vision` as a local skill under `manifest/skills/vision/`.
- [x] 8.5 Test with three fixture images: a clear photo, a document page, and a receipt — assert non-empty sensible output per mode.

## 9. Plugin: macos-control

- [x] 9.1 Create `plugins/macos_control/` Python package + MCP server scaffolding.
- [x] 9.2 Implement `list_windows`, `focus_app`, `focus_window` using `osascript` (System Events).
- [x] 9.3 Implement `screenshot_full`, `screenshot_window`, `screenshot_region` using `screencapture` with appropriate flags.
- [x] 9.4 Implement `type_text`, `key_combo`, `run_applescript`, `notify`.
- [x] 9.5 Wrap every tool to detect TCC permission errors and return a structured `{ok:false, error:"missing_permission", needed, how_to_fix}` instead of raising.
- [x] 9.6 Author `plugins/macos_control/README.md` with exact System Settings → Privacy & Security paths for Accessibility, Screen Recording, and Automation.
- [x] 9.7 Manifest entry: `manifest/mcp/macos-control.yaml` registering the local server.
- [x] 9.8 Smoke test on the user's machine: focus Finder, screenshot the active window, send notification. *(Live: `list_windows` via real osascript exercised the path end-to-end and returned a graceful structured `timeout` (Accessibility not granted to the responsible app + no interactive prompt) — exactly the missing-grant handling §9.5 specifies. Surfaced + fixed a real bug (uncaught `TimeoutExpired`). Full interactive focus/screenshot/notify smoke needs the TCC grants in place — run `hermes doctor --fix` first. Tool logic + TCC mapping: 13/13 unit tests.)*

## 12. Seed the user's real manifest (into the PRIVATE `hermes_config` repo)
<!-- Per design.md Decision 20: capture goes into the private hermes_config repo via --manifest-dir, NOT into this public hermes_setup repo. Requires §18 plumbing first. -->

- [x] 12.1 Create the private `hermes_config` repo on gitcode; `hermes capture --manifest-dir ~/hermes_config` against the user's current `~/.claude/` machine (depends on §18).
- [x] 12.2 Diff-review the generated `~/hermes_config/manifest/` for any missed secrets and confirm `$HOME` paths were templated to `${HOME}` (settings.json, hook commands, MCP env). Pay attention to `settings.json`, MCP env maps, and any skill that pulls credentials at install time.
- [x] 12.3 Hand-edit `~/hermes_config/manifest/.redact.yaml` to plug any pattern gaps discovered in 12.2; re-run capture; repeat until clean.
- [x] 12.4 Populate `~/hermes_config/secrets.env` with real values for the variables the manifest references (e.g. any MCP/plugin secrets). `secrets.env` stays gitignored even in the private repo. *(no secrets needed — this config has 0 MCP servers and no secret-shaped values; secrets.env.example is empty.)*
- [x] 12.6 Commit the manifest to the PRIVATE `hermes_config` repo. Do NOT commit `secrets.env`. The public `hermes_setup` repo receives nothing personal. *(Local commit done in ~/hermes_config (private GitHub: Dmitriy403/hermes_config). `git push` is the user's manual step — the harness hard-blocks pushing personal config to an external repo.)*
- [ ] 12.7 Test full bootstrap on a clean macOS VM (Multipass or UTM): `curl|bash` the public tool, then `hermes install --manifest-dir <clone of hermes_config>`; grant Accessibility & Screen Recording, then confirm `hermes verify` returns clean and the v0.1.0 plugins (vision, macos-control) respond to a basic smoke check. *(MANUAL: runbook at [tools/vm-bootstrap-test.md](tools/vm-bootstrap-test.md) — Flow B drives BYO-config via `HERMES_CONFIG_URL=… curl|bash`; gates B.1–B.5. The post-§18.6–§18.10 install.sh handles both bootstrap paths.)*

## 18. Two-repo support: manifest_dir / tool_root split + $HOME templating
<!-- New v0.1.0 work from design.md Decision 20. Required for the public-tool / private-config split to function. -->

- [x] 18.1 In `paths.py`, split `tool_root()` (bin/, tools/, installed package) from `manifest_dir()` (resolved from `--manifest-dir` arg → `HERMES_MANIFEST_DIR` env → `tool_root()/manifest` default). Update `permissions_yaml_path()` etc. to use `manifest_dir()`; keep `probe_binary()` + sandbox-rules on `tool_root()`.
- [x] 18.2 Thread `--manifest-dir` through `hermes capture`, `hermes install`, `hermes verify` (and `capabilities`). Default = factory `manifest/` so out-of-box install still works.
- [x] 18.3 Implement `$HOME` templating: capture rewrites the current `$HOME` prefix → `${HOME}` in settings.json values, MCP `command`/`env`, and hook command strings; install expands `${HOME}` back to the target home. Leave CLAUDE.md verbatim. Only rewrite the current-home prefix.
- [x] 18.4 Prune auto-accumulated over-specific permission entries on capture (e.g. `Bash(mkdir -p /Users/<me>/.claude/skills/<x>)`) — or document them as expected; confirm they don't break install on a different username.
- [x] 18.5 Unit tests: `manifest_dir` resolution precedence (flag > env > default); `$HOME` round-trip (capture templates → install expands → matches original on same home, and produces correct paths on a different home); capture into a separate `--manifest-dir` leaves `tool_root` untouched.
- [x] 18.6 Ship a factory `manifest/hermes.yaml` in the public tool repo registering the no-secret bundled plugins so bare `hermes install` works on a clean machine — closes the gap behind §18.2's "Default = factory `manifest/` so out-of-box install still works." Default-on set: `vision` (skill), `macos-control` (mcp), `voice` (mcp). `telegram-bot` and `backups` remain opt-in (registered only when the user layers a private `hermes_config` via `--manifest-dir` / `HERMES_CONFIG_URL`). *(Done: manifest/hermes.yaml committed; Manifest.load succeeds; resolve_manifest_env reports no missing required secrets.)*
- [x] 18.7 Extend `plugins_registry.PluginInfo` with `brew_deps: tuple[str,...]` (`voice` → `whisper-cpp`, `ffmpeg`; `backups` → `restic`; others empty). `hermes install` pre-flights: for each registered plugin, **warn** (not fail) on missing `brew_deps` with the exact `brew install <pkg>` line; `hermes verify` adds a `brew-deps` drift component listing absent pre-reqs (informational — plugins remain fail-soft at runtime per Decision 18). *(Done: PluginInfo.brew_deps; installer.step_plugin_brew_deps (between layer_b and plugin_packages) logs `warn: plugin <X> pre-reqs missing — brew install …`; verify._verify_brew_deps emits a `brew-deps` DriftRecord per plugin (match/missing). Live verify on this Mac flags voice (missing whisper-cpp+ffmpeg) and matches backups (restic installed).)*
- [x] 18.8 `install.sh`: add `HERMES_CONFIG_URL` (+ `HERMES_CONFIG_DIR`, default `~/hermes_config`). If `HERMES_CONFIG_URL` is set, clone (or fast-forward) the config repo to `HERMES_CONFIG_DIR`, route `HERMES_SECRETS_FILE` to `$HERMES_CONFIG_DIR/secrets.env` (not the tool repo), and hand off `hermes install --manifest-dir $HERMES_CONFIG_DIR`. If unset, fall back to the factory path (§18.6). *(Done: new §3.5 in install.sh clones the config repo when HERMES_CONFIG_URL is set; secrets route to MANIFEST_ROOT/secrets.env via SECRETS_EXAMPLE+SECRETS_DST; run_hermes_install() passes --manifest-dir conditionally. shellcheck + bash -n clean.)*
- [x] 18.9 Tests: factory-only `hermes install` on a tmp `tool_root` carrying the new factory `hermes.yaml` resolves `macos-control`/`vision`/`voice` and writes no telegram/backup launchd jobs; pre-req warning lists missing brew binaries for `voice`/`backups` when their bins are absent; `install.sh` with `HERMES_CONFIG_URL` set (mocked `git clone`) routes secrets to `HERMES_CONFIG_DIR` and invokes `hermes install --manifest-dir <that dir>` (`bash -n` + a small dry-run shell test). *(Done: 3 new tests in test_plugin_orchestration.py — test_factory_install_dry_run_registers_no_secret_plugins, test_step_plugin_brew_deps_warns_for_missing_voice_deps, test_verify_emits_brew_deps_drift_for_voice — plus tests/test_install_sh.py with bash-n syntax + HERMES_CONFIG_URL flow + factory path. Full suite 56/56.)*
- [x] 18.10 README bootstrap section: document both flows — "zero-config: `curl … | bash` → factory plugins" and "BYO config: `HERMES_CONFIG_URL=… curl … | bash` → private manifest". *(Done: README "Bootstrap a new machine" rewritten with sub-sections "Zero-config — factory plugins, no secrets" + "BYO-config — layer your private hermes_config" + an env-override table including HERMES_CONFIG_URL/HERMES_CONFIG_DIR. §6.5/§12.7 now have something concrete to verify on a clean macOS VM.)*
- [x] 18.11 Fix factory false-opt-in for `backups`: the public tool ships `manifest/backups.yaml` as a generic starter, and `_registered_plugins` reads the file's existence as the backups opt-in signal — so on a zero-config `curl|bash` the backups plugin (and its launchd job) get installed without `RESTIC_PASSWORD`. Rename the starter to `manifest/backups.yaml.example` (mirrors `secrets.env.example`). No other call sites depend on the factory-side file. Surfaced by the fresh-user `hermestest` run on 2026-05-30.
- [x] 18.12 Fix `brew_deps` formula↔binary mismatch: `voice.brew_deps = ("whisper-cpp", "ffmpeg")` but `brew install whisper-cpp` installs the binary as `whisper-cli` — `which("whisper-cpp")` is always None and the drift never clears. Adopt `"formula:binary"` syntax (binary optional, defaults to formula). `voice` becomes `("whisper-cpp:whisper-cli", "ffmpeg")`; the warning still says `brew install whisper-cpp` (formula), but `which()` checks `whisper-cli` (binary).
- [x] 18.13 Fix `pipx inject` re-symlink: `installer.step_plugin_packages` calls `pipx inject … --include-apps` without `--force`. If the package is already in the venv from a prior attempt, pipx skips and `--include-apps` is silently ignored, leaving venv-bin scripts un-symlinked to `~/.local/bin/`. Add `--force` (we already entered the inject branch because `which(console_script)` was None — re-doing the install is the desired behavior).
- [x] 18.14 Tests for 18.11–18.13: factory `_registered_plugins` returns no `backups` when only the `.example` is present; brew_deps `formula:binary` parsing — warning uses formula, `which()` checks binary; `pipx inject` argv now includes `--force` + `--include-apps`.
- [ ] 18.15 Re-run the fresh-user `hermestest` script ([/Users/Shared/hermestest-test/run.sh](/Users/Shared/hermestest-test/run.sh)) and confirm gates A.1–A.4 + A.6 clean post-fix: no `backups` install on the factory path; `hermes-{macos-control,voice}` resolve via PATH; `hermes verify` shows `brew-deps voice match` after `brew install whisper-cpp`.
- [ ] 18.16 Fix shallow-clone divergence in `install.sh`. The "update existing checkout" branch ran `git pull --ff-only origin <ref> || true` — with `--depth 1` clones, a later shallow fetch can create graft points so `git` sees the local + remote as "diverged" even when they are linear, and `--ff-only` then refuses. The `|| true` swallows the failure → the local clone stays on stale code → subsequent `pipx install --editable` uses old code → every install-side fix (§18.6-§18.13) is silently ignored. Replace with `fetch + reset --hard origin/<ref>`: the clone is an installer-owned mirror, not a user dev branch; resetting is the correct semantics and bypasses both the shallow-graft case and any accidental local edits. Surfaced by the second hermestest run (2026-05-30 19:25).

## 13. Documentation

- [x] 13.1 Expand `README.md` with the full bootstrap URL, the three CLI commands, the secrets workflow, and the supported platform matrix.
- [x] 13.2 Add a short `SECURITY.md` explaining the redaction model, what is and isn't captured, and how to rotate a leaked secret if one slips through.
- [x] 13.3 Document each plugin in `plugins/<name>/README.md`: what it does, env vars it reads, required macOS permissions, smoke-test commands. *(v0.1.0 plugins done: plugins/macos_control/README.md + manifest/skills/vision/files/SKILL.md. telegram/voice/backups READMEs ship with v0.2.0.)*
- [x] 13.4 Add a `CHANGELOG.md` and tag `v0.1.0` once the seed manifest in §12 is committed. *(CHANGELOG.md written. `git tag v0.1.0` is a manual step after §12 + the §6.5 VM smoke — noted in CHANGELOG.)*

## 14. Security manifest (`permissions.yaml`) and Layer A enforcement

- [x] 14.1 Define the `permissions.yaml` schema in `src/hermes/manifest.py` as typed dataclasses: `filesystem` (write-exec / write / read / forbidden), `shell` (allow / ask / deny), `network` (domains, default), `mcp` (enabled, disabled), `tcc` (per-category with `required-by[]` lists; `automation.targets[]` and `files[]` are sub-structures).
- [x] 14.2 Author `manifest/permissions.yaml` using the starter content recorded in `design.md` Appendix A. Verify it parses against the dataclass schema from §14.1, that the dataclasses round-trip (load → save → load is byte-stable), and that `network.default: ask` is a recognised enum value alongside `allow`/`deny`.
- [x] 14.3 Implement `src/hermes/hooks/pretooluse_enforce.py`: reads `manifest/permissions.yaml`, takes the tool-call payload via stdin, returns a decision (allow / deny / ask) with a short rationale. Handles `Write`, `Edit`, `Bash`, `WebFetch`, and `mcp__*` tool families.
- [x] 14.4 Wire `hermes install` to register the Layer A hook in `~/.claude/settings.json` and to merge it with any user-authored hooks present in the manifest.
- [x] 14.5 Implement `hermes capabilities` command: prints a human-readable table summarising the effective `permissions.yaml` plus its overlay sources (base / per-project / project-local). Supports `--json` for machine consumption.
- [x] 14.6 Capture round-trip (per `design.md` Q10 option C): when a `manifest/permissions.yaml` is generated by `hermes capture`, start from the Appendix A starter content and then OVERLAY machine-discovered facts: (a) for each MCP server found in `~/.claude/settings.json` whose name does not already match an entry in `mcp.enabled`, add a glob covering it; (b) for each `WebFetch(domain:<X>)` entry in `permissions.allow`, add `<X>` to `network.domains` if missing. Do NOT translate broad `Bash(*)/Edit(*)/Write(*)/Read(*)` patterns from the existing `settings.json` — these are explicitly superseded by the starter's structured policy.
- [x] 14.7 Unit tests for the Layer A hook: assert that a `Write` to `~/.ssh/id_rsa` is denied, a `Bash("sudo rm -rf /")` is denied, a `WebFetch("https://example.com")` is denied when `example.com` is not in `network.domains`, and a `Write` to `~/projects/foo` is allowed.
- [x] 14.8 Document the security model in `SECURITY.md`: Layer A always-on, Layer B opt-in (deferred), Layer C VM mode (out of scope). Explain the responsible-process / TCC interaction with a short example.

## 15. Probe binary `bin/hermes-probe-tcc`

- [x] 15.1 Create `tools/probe-tcc/` with the layout: `Sources/`, `Info.plist`, `entitlements.plist` (empty for v1), `build.sh`, `verify.sh`, `README.md`. Add `tools/probe-tcc/build/` to `.gitignore`.
- [x] 15.2 Author `Info.plist` with `CFBundleIdentifier=org.hermes.probe-tcc`, `CFBundleExecutable=hermes-probe-tcc`, `LSUIElement=true`, and all required Usage Description keys (`NSAppleEventsUsageDescription`, `NSMicrophoneUsageDescription`, `NSCameraUsageDescription`, `NSDocumentsFolderUsageDescription`, `NSDesktopFolderUsageDescription`, `NSDownloadsFolderUsageDescription`, `NSSpeechRecognitionUsageDescription`).
- [x] 15.3 Implement `Sources/main.swift` and one file per probe (`ScreenRecording.swift`, `Accessibility.swift`, `Automation.swift`, `FullDiskAccess.swift`, `Media.swift`, `InputMonitoring.swift`, `Files.swift`, `ResponsibleProcess.swift`, `Output.swift`). Use the silent preflight APIs listed in `specs/probe-tcc/spec.md` (no `requestAccess` variants in default mode).
- [x] 15.4 Implement responsible-process detection: walk parent pids, identify the first `.app/Contents/MacOS/*` ancestor, resolve its bundle id, emit the full chain in `responsible_process.chain[]`.
- [x] 15.5 Implement the v1 JSON output schema (`https://hermes/probe-tcc/v1`) per `specs/probe-tcc/spec.md`. Include a `--json` flag and a human-readable default formatter for direct CLI use.
- [x] 15.6 Author `build.sh`: `swiftc` with `-target arm64-apple-macosx13.0`, `-Xlinker -no_uuid`, embed Info.plist via `-sectcreate __TEXT __info_plist`, ad-hoc `codesign` with `--identifier org.hermes.probe-tcc`, verify, print cdhash.
- [x] 15.7 Author `verify.sh`: confirms signature, identifier, and embedded Info.plist match expectations; intended to run in CI on every commit that touches `tools/probe-tcc/`.
- [x] 15.8 Add `manifest/probe-tcc.yaml` sidecar storing the `expected_cdhash` value; update on each rebuild and commit alongside `bin/hermes-probe-tcc`.
- [x] 15.9 Implement `--self-test` mode that re-runs the matrix and maps "API failed because of Seatbelt" errors to `status: blocked_by_sandbox`.
- [x] 15.10 Test the probe on the maintainer's machine: confirm `--json` returns plausible status for every category, `responsible_process.bundle_id` matches the actual terminal, and `cdhash` from `codesign --display` matches `self.cdhash` in the JSON.

## 16. `hermes doctor` and `~/.hermes/probe-cache.json`

- [x] 16.1 Create `src/hermes/doctor/` with `__init__.py`, `cache.py` (probe-cache schema + atomic read/write), `probe.py` (spawn `bin/hermes-probe-tcc`, parse JSON, pass `--automation-targets`/`--expect-files`), `classify.py` (the three-axis detector), `report.py` (human + JSON formatters), `fix.py` (deep-link opener for `--fix` mode).
- [x] 16.2 Implement `~/.hermes/` creation with mode `0700` + fallback to `~/Library/Application Support/Hermes/`. Add `paths.HERMES_HOME` helper.
- [x] 16.3 Implement `probe-cache.json` schema v1 (per `specs/doctor/spec.md`). Validate on load, back up corrupt files to `probe-cache.broken-<ISO8601>.json`, write atomically via temp file + rename. Ring buffer history is capped at 20 events.
- [x] 16.4 Implement the three-axis classifier per `specs/doctor/spec.md`: OK / REBUILD_DETECTED / TERMINAL_SWAP / REVOKED_OR_NEVER / FIRST_TIME_SEEN / BLOCKED_BY_SANDBOX. Append `cdhash_changed` and `responsible_bundle_changed` events to the cache's `history[]`.
- [x] 16.5 Implement deep-link Settings URLs for every TCC category: Accessibility (`Privacy_Accessibility`), Screen Recording (`Privacy_ScreenCapture`), Automation (`Privacy_Automation`), Full Disk Access (`Privacy_AllFiles`), Files & Folders (`Privacy_Files-and-Folders`), Microphone (`Privacy_Microphone`), Camera (`Privacy_Camera`), Input Monitoring (`Privacy_ListenEvent`).
- [x] 16.6 Wire CLI modes: `--check` (default), `--fix`, `--warmup`, `--reset <CATEGORY>`, `--mdm-profile`, `--json`, `--strict`, `--exit-zero`. Implement exit-code semantics per spec (`0`/`1`/`2`/`3`/`10`/`64`).
- [x] 16.7 Implement sandbox-aware mode: if the parent chain includes `sandbox-exec`, re-invoke the probe under `sandbox-exec -f <profile> bin/hermes-probe-tcc --self-test` and compare. Render a sandbox×TCC matrix in the report.
- [x] 16.8 Implement opt-in `SessionStart` hook: when `manifest/hermes.yaml` sets `hooks.doctor_on_session_start: true`, `hermes install` adds an entry that calls `hermes doctor --check --exit-zero --json > /dev/null` so doctor never blocks Claude startup. Default OFF. *(Done in §4: `installer._build_settings` injects the SessionStart entry; covered by tests/test_install.py::test_install_doctor_hook_injected. Manifest gained `doctor_on_session_start` read from `hooks_config` in hermes.yaml.)*
- [x] 16.9 Implement `hermes doctor --mdm-profile`: emit a `.mobileconfig` PPPC payload for Accessibility, Automation, and Files & Folders. Explicitly list Screen Recording and Full Disk Access as "manual grant required" in the report header.
- [x] 16.10 Integration test on the maintainer's machine: first run with no cache (`FIRST_TIME_SEEN`), grant 2 permissions in Settings, second run (mixed `OK` + `REVOKED_OR_NEVER`), rebuild probe, third run (everything classified `REBUILD_DETECTED`), then re-grant and confirm fourth run is clean `OK` for all required categories.
- [x] 16.11 Document `hermes doctor` in the repo root `README.md` with a short troubleshooting section: "if TCC seems broken after a probe rebuild, run `hermes doctor --fix`". Add the same flow to `tools/probe-tcc/README.md` for maintainers.
- [x] 16.12 Implement Layer B auto-detect in `src/hermes/doctor/probe.py`: read `permissions.yaml` for `security.layer_b.enabled` and `security.layer_b.profile_path`; honor the `--with-sandbox=PATH` override. Skip the sandboxed pass and warn loudly if doctor itself is already running under a `sandbox-exec` ancestor.
- [x] 16.13 Implement the 2×2 classifier in `src/hermes/doctor/classify.py`: take baseline-pass and sandboxed-pass JSON outputs, emit per-category cell (`ALL_OK` / `SANDBOX_BLOCKED` / `TCC_DENIED` / `BOTH_BLOCKED`), and flag `ANOMALY` (with both `responsible_process` values) when baseline is denied but sandboxed is granted.
- [x] 16.14 Implement profile gap report in `src/hermes/doctor/report.py`: aggregate `required_sandbox_rules` from blocked categories, deduplicate identical rules across categories (listing consumers), name the active profile path. Surface drift between `permissions.yaml: security.layer_b.profile_path` and the actually-loaded file.
- [x] 16.15 Implement `--suggest-sandbox-patch` mode in `src/hermes/doctor/fix.py`: emit a unified diff against the current profile that inserts only the missing rules, deterministically placed (mach-lookup near other mach-lookup lines, etc.), patchable via `patch -p0`.
- [x] 16.16 Integration test for Layer B differential matrix on the maintainer's machine: create a deliberately incomplete `permissions.yaml` (omit Screen Recording mach-lookup), run `hermes install` to generate `~/.hermes/profile.sb`, run `hermes doctor`, assert `screen_recording` is classified `SANDBOX_BLOCKED`, run `hermes doctor --suggest-sandbox-patch`, apply the diff, re-install, re-run doctor, assert `screen_recording` is `ALL_OK`. *(Validated LIVE 2026-05-29 on the real machine against a genuinely-granted category (Files): full generated profile → `ALL_OK`; stripped profile → `SANDBOX_BLOCKED` + gap report names the exact rules; `--suggest-sandbox-patch` emits exactly them. Used `--with-sandbox` + a /tmp profile to avoid mutating ~/.claude; the generator is the same one `step_layer_b` uses.)*

- [x] 16.17 Add a "plugin dependencies" section to `hermes doctor` (per design.md Decision 18): run `shutil.which` checks for each registered plugin's external binary (`restic`, `rclone`, `whisper-cpp`, `ffmpeg`, …) and list every missing one with its `brew install` command. Report-only — doctor never installs.

## 17. Layer B sandbox profile generation

- [x] 17.1 Author `tools/probe-tcc/sandbox-rules.yaml` mapping each TCC category to its required Seatbelt `mach-lookup` / `appleevent-send` / `file-read*` allow rules. Single source of truth shared by probe (Swift) and install-time generator (Python).
- [x] 17.2 Embed `sandbox-rules.yaml` into the probe binary at build time (linker `-sectcreate` or read-at-startup from a path-relative-to-binary) so the probe and the generator stay in sync without runtime coordination. *(v1 approach: instead of build-time embedding, sync is enforced by `tools/probe-tcc/check_sandbox_rules.py` — asserts the Swift `SandboxRules.swift` constants set-equal `sandbox-rules.yaml`; wired into `verify.sh`. Lighter than codegen, catches drift in CI.)*
- [x] 17.3 Implement `src/hermes/install/sandbox_profile.py`: read `permissions.yaml` and `sandbox-rules.yaml`, emit a deterministic Seatbelt profile to a writer (used by install and by tests).
- [x] 17.4 Translate `permissions.yaml: filesystem.{write-exec, write, read}` into `file-read*` / `file-write*` allow rules; `filesystem.forbidden` into explicit denies (defense-in-depth even though `(deny default)` covers most cases).
- [x] 17.5 Translate `permissions.yaml: shell.allow` into a small `(allow process-exec*)` allowlist; rely on `permissions.allow` in Claude Code settings for the policy-level enforcement.
- [x] 17.6 Translate `permissions.yaml: tcc.*` into the corresponding rules from `sandbox-rules.yaml`. For Automation, fan out per `target.bundle_id`.
- [x] 17.7 Wire profile generation into `hermes install` (per `specs/install/spec.md`): only when `security.layer_b.enabled: true`, write to `~/.hermes/profile.sb` atomically with mode `0600`, log byte-diff if regenerated content differs from existing. *(Done in §4: `installer.step_layer_b` generates the profile (0600, atomic via Mutator) when Layer B is enabled; covered by test_install_layer_b_generates_profile.)*
- [x] 17.8 Make profile generation idempotent: same inputs → byte-identical output (stable rule ordering, no timestamps). Add a unit test that runs the generator twice against the same manifest and asserts byte equality.
- [x] 17.9 Add stale-profile warning: if `~/.hermes/profile.sb` exists but `security.layer_b.enabled` is now `false`, install logs a warning naming the stale file and `hermes verify` reports drift. Do NOT silently delete (user may have hand-edited). *(Done: §4 `step_layer_b` warns + leaves the file; §5 `verify._verify_layer_b` reports the stale profile as `extra` drift.)*
- [x] 17.10 Add `hermes run` command: a thin wrapper that resolves the active profile (`security.layer_b.profile_path` or `--with-sandbox` override) and execs `claude` under `sandbox-exec -f <profile>`. If Layer B is disabled, `hermes run` simply execs `claude` directly and logs that fact.
