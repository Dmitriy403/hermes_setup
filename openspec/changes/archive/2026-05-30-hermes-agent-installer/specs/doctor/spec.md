## ADDED Requirements

### Requirement: `hermes doctor` is a read-only TCC and capability checkup
The system SHALL provide a `hermes doctor` command that, without prompting the user or mutating any state, reports whether the macOS TCC permissions required by the manifest are currently granted to the responsible process (typically the host terminal) and whether the on-disk probe binary matches the cached identity. The base `hermes doctor` invocation MUST be safe to run repeatedly and from automated contexts (CI, hooks).

#### Scenario: Base invocation is read-only
- **WHEN** `hermes doctor` runs without `--fix` or `--warmup`
- **THEN** no TCC prompts appear
- **AND** no files outside `~/.hermes/` are modified
- **AND** `~/.hermes/probe-cache.json` MAY be created or updated to reflect the latest probe results

#### Scenario: Output is structured and actionable
- **WHEN** `hermes doctor` finishes
- **THEN** stdout contains, for every TCC category required by the manifest, the status and (if denied or misaligned) a deep-link URL of the form `x-apple.systempreferences:com.apple.preference.security?...` pointing at the System Settings pane the user must open
- **AND** the exit code reflects the worst classification found (see exit-code requirement below)

### Requirement: Doctor exit-code semantics
`hermes doctor` MUST exit with a code that conveys aggregate health to scripts and hooks:
- `0` — all required permissions granted to the current responsible process.
- `1` — misalignment: at least one required permission is granted but to a different bundle id (e.g., previously running terminal).
- `2` — at least one required permission is missing.
- `3` — at least one probe was suppressed by the active sandbox profile (Seatbelt blocked the call before TCC could answer).
- `10` — internal probe error (probe binary missing, killed by SIGKILL on first call, Info.plist key missing, etc.).
- `64` — usage error (invalid CLI arguments).

When multiple conditions hold, the higher exit code wins (e.g., `10` beats `2`, `2` beats `1`).

`--strict` SHALL elevate "extra grants" (permissions granted but not required by the manifest) and `1`-class misalignments to exit code `2`. `--exit-zero` SHALL force exit code `0` regardless of findings, leaving the structured report as the only signal.

#### Scenario: Exit code reflects worst class
- **WHEN** the probe reports one `denied` category and one `misaligned` category
- **THEN** `hermes doctor` exits `2`

### Requirement: Doctor invokes a separately-installed probe binary
`hermes doctor` MUST locate the probe binary at `bin/hermes-probe-tcc` (relative to the repo root) or, if the repo root is not on PATH, via the path stored in `~/.hermes/probe-cache.json`. It MUST NOT bundle probe logic into the Python CLI; the probe is its own artifact governed by the `probe-tcc` capability.

#### Scenario: Missing probe binary is a hard error
- **WHEN** `hermes doctor` cannot find an executable probe binary
- **THEN** the command exits `10` with a message instructing the user to run `tools/probe-tcc/build.sh`
- **AND** `~/.hermes/probe-cache.json` is not modified

### Requirement: Probe input contract
`hermes doctor` MUST invoke the probe binary as a child process with `--json` and pass the manifest-derived expectations as CLI arguments: `--automation-targets=<comma-separated bundle ids>` and `--expect-files=<comma-separated absolute paths>`. The probe MUST NOT read the manifest itself. This keeps the probe a dumb collector and the doctor the sole consumer of manifest semantics.

#### Scenario: Automation targets are read from the manifest
- **WHEN** the manifest's `permissions.tcc.automation.targets` lists `com.apple.finder` and `com.apple.systemevents`
- **AND** `hermes doctor` runs
- **THEN** the probe binary is invoked with `--automation-targets=com.apple.finder,com.apple.systemevents`

### Requirement: Probe cache lives at `~/.hermes/probe-cache.json`
Doctor SHALL maintain a per-user cache at `~/.hermes/probe-cache.json`. The cache MUST be created with mode `0700` for the directory and `0600` for the file. If `~/.hermes/` is not writable, doctor SHALL fall back to `~/Library/Application Support/Hermes/probe-cache.json` and log a warning. The cache MUST conform to schema `https://hermes/probe-cache/v1` and contain:
- `probe.cdhash`, `probe.bundle_id`, `probe.binary_path`, `probe.first_seen`, `probe.last_seen`
- `responsible_process_at_grant.bundle_id`, `.name`, `.first_seen_with_this_bundle`
- `grants.<category>.{status, granted_for_cdhash, granted_for_bundle, first_observed, last_verified}`, with nested `by_target` for `automation` and per-path entries for `files`
- `history[]` — a ring buffer of at most 20 events recording `cdhash_changed` and `responsible_bundle_changed` transitions

Doctor MUST update the cache atomically via temp file + `rename(2)`. No file lock is required; concurrent writers may race and the last writer wins.

#### Scenario: Cache is recreated when corrupted
- **WHEN** `~/.hermes/probe-cache.json` exists but fails JSON parsing or schema validation
- **THEN** doctor backs up the broken file to `~/.hermes/probe-cache.broken-<ISO8601>.json`
- **AND** creates a fresh empty cache
- **AND** continues the probe run

### Requirement: Three-axis state classifier
For each required TCC category, doctor MUST classify the current state along three axes by comparing the live probe result against the cached grants. Classifications and their meanings:
- `OK` — `status == granted` AND `granted_for_cdhash == probe.cdhash` AND `granted_for_bundle == probe.responsible.bundle_id`.
- `REBUILD_DETECTED` — `status == denied` AND a previous grant exists but `granted_for_cdhash != probe.cdhash`. The doctor MUST append a `cdhash_changed` event to `history[]` and label the report with the from/to cdhash diff.
- `TERMINAL_SWAP` — `status == denied` AND `granted_for_bundle != probe.responsible.bundle_id`. The doctor MUST append a `responsible_bundle_changed` event and label the report with the from/to bundle id.
- `REVOKED_OR_NEVER` — `status == denied` AND cached cdhash and bundle both match. No history event; the report shows "permission revoked or never granted".
- `FIRST_TIME_SEEN` — `status == granted` AND no prior cache entry exists. Cache entry is populated.
- `BLOCKED_BY_SANDBOX` — probe returned this status because the active sandbox profile suppressed the API call. In this state the cache MUST NOT be updated for the affected category and the report MUST flag the sandbox profile path.

#### Scenario: Rebuild is detected and reported
- **GIVEN** `~/.hermes/probe-cache.json` records `screen_recording.granted_for_cdhash` as `aaaa...`
- **WHEN** the probe binary is rebuilt (its cdhash is now `bbbb...`)
- **AND** `hermes doctor` runs
- **THEN** screen_recording is classified `REBUILD_DETECTED`
- **AND** the report includes the line `probe-tcc cdhash changed: aaaa... → bbbb...`
- **AND** the user is instructed to re-grant Screen Recording in System Settings

#### Scenario: Terminal swap is detected and reported
- **GIVEN** the cache records `responsible_process_at_grant.bundle_id` as `com.googlecode.iterm2`
- **WHEN** the user runs `hermes doctor` from a different terminal whose bundle id is `com.mitchellh.ghostty`
- **AND** the probe reports `screen_recording.status == denied`
- **THEN** the category is classified `TERMINAL_SWAP`
- **AND** the report includes `responsible bundle changed: com.googlecode.iterm2 → com.mitchellh.ghostty`

### Requirement: Modes — `--check`, `--fix`, `--warmup`, `--reset`, `--mdm-profile`, `--json`
Doctor SHALL support the following modes, which MUST be mutually exclusive (with the exception of `--json`, which composes with any other mode):
- `--check` (default) — fully read-only; never opens System Settings, never triggers TCC prompts.
- `--fix` — sequentially opens the System Settings deep-link for each missing/misaligned category and pauses for the user to press Enter before moving to the next.
- `--warmup` — for each category whose probe status is `notDetermined`, triggers the corresponding API in a mode that does present the TCC prompt. Intended for first-time setup.
- `--reset <CATEGORY>` — invokes `tccutil reset <CATEGORY>` for the named category (e.g., `ScreenCapture`, `Accessibility`, `Automation`). Destructive and confirmed-by-default; suppress confirmation with `--yes`.
- `--mdm-profile` — emits a `.mobileconfig` PPPC payload covering the categories that PPPC supports (Accessibility, Automation, Files & Folders). Categories that cannot be granted via MDM (Screen Recording, Full Disk Access) are explicitly listed as "must be granted manually".
- `--json` — machine-readable output, compatible with any of the above modes.

#### Scenario: `--check` is silent and idempotent under all-ok state
- **WHEN** `hermes doctor --check --json` runs while all required permissions are granted and `cdhash`/`bundle` match the cache
- **THEN** the command exits `0`
- **AND** stdout is a JSON document with `summary.granted == summary.total`
- **AND** the only mutation is updating `last_verified` timestamps in the cache

### Requirement: Sandbox-aware probing — differential 2×2 matrix
When Layer B is detected (either `permissions.yaml: security.layer_b.enabled == true` resolves to a readable profile, or the caller passes `--with-sandbox=PATH`), doctor MUST run two probe invocations and classify each TCC category along a 2×2 matrix:
1. **Baseline pass** — `bin/hermes-probe-tcc --json --automation-targets=... --expect-files=...`, run without any sandbox wrapping. This gives the "truth from TCC".
2. **Sandboxed pass** — `sandbox-exec -f <profile> bin/hermes-probe-tcc --self-test --json --automation-targets=... --expect-files=...`, run with the active profile. This gives "what claude will see under Layer B".

For each category, doctor MUST classify into one of the four cells:
- `ALL_OK` — baseline granted, sandboxed granted.
- `SANDBOX_BLOCKED` — baseline granted, sandboxed denied. The Seatbelt profile is the cause.
- `TCC_DENIED` — baseline denied, sandboxed denied. TCC is the cause.
- `BOTH_BLOCKED` — both blocked. Sandbox must be fixed first (else doctor cannot see the moment TCC unlocks), then TCC.

A `baseline denied + sandboxed granted` result is `ANOMALY` — theoretically impossible under macOS semantics (sandbox checks run *before* TCC, so a sandboxed pass should never have *more* access than baseline). When observed, doctor MUST emit exit code `10` and include both passes' `responsible_process` values in the report; the most common real cause is the two passes seeing different responsible processes.

#### Scenario: Differential matrix distinguishes the four cells
- **GIVEN** `permissions.yaml: security.layer_b.enabled: true` and `~/.hermes/profile.sb` exists
- **AND** Screen Recording is granted to the responsible terminal in System Settings
- **AND** the profile omits `(allow mach-lookup (global-name "com.apple.windowserver.active"))`
- **WHEN** `hermes doctor` runs
- **THEN** the `screen_recording` row is classified `SANDBOX_BLOCKED`
- **AND** the report names `~/.hermes/profile.sb` as the active profile
- **AND** the baseline pass result for `screen_recording` is `granted`

### Requirement: Sandbox column hidden when Layer B is not active
When neither `permissions.yaml: security.layer_b.enabled == true` nor `--with-sandbox=PATH` is in effect, doctor MUST NOT spawn a sandboxed pass and MUST NOT render a "Sandbox" column in human output. The Layer B columns also MUST NOT appear in `--json` output beyond the existing `sandbox.{active, profile_path}` block (which reports `active: false`). Discoverability of Layer B belongs to documentation (`SECURITY.md`, `design.md` Decision 14), not to a permanently-empty column.

#### Scenario: Default output has no sandbox column
- **GIVEN** `permissions.yaml` does not enable Layer B
- **WHEN** `hermes doctor` runs without `--with-sandbox`
- **THEN** the human-readable report contains no per-category "Sandbox" column
- **AND** stdout does not include the string `BLOCKED_BY_SANDBOX`

### Requirement: Profile gap report aggregates `required_sandbox_rules`
When at least one category is classified `SANDBOX_BLOCKED` or `BOTH_BLOCKED`, doctor MUST emit a "profile gap report" that aggregates the `required_sandbox_rules` arrays produced by the probe (per the `probe-tcc` capability). The report MUST:
1. Group rules by the category that requires them.
2. Deduplicate identical rules across categories (e.g., `(allow mach-lookup (global-name "com.apple.tccd"))` typically appears in multiple categories — print it once with a list of consumers).
3. Name the profile path and the manifest's `security.layer_b.profile_path` (if these differ — drift between manifest and disk).
4. Direct the user to `hermes doctor --suggest-sandbox-patch` for a unified diff.

The report MUST NOT modify `~/.hermes/profile.sb` itself. Profile editing is the user's action, symmetric to how the doctor never grants TCC permissions itself.

#### Scenario: Gap report names blocked rules and consumers
- **GIVEN** two categories (`screen_recording`, `microphone`) are `SANDBOX_BLOCKED` and both probes emitted `(allow mach-lookup (global-name "com.apple.tccd"))` in their `required_sandbox_rules`
- **WHEN** `hermes doctor` runs
- **THEN** the report contains `(allow mach-lookup (global-name "com.apple.tccd"))` exactly once
- **AND** the line lists both `screen_recording` and `microphone` as consumers

### Requirement: `--suggest-sandbox-patch` emits a unified diff
The `--suggest-sandbox-patch` mode SHALL print a unified diff against the current `~/.hermes/profile.sb` whose application would close every `SANDBOX_BLOCKED` gap reported on this run. The diff MUST:
1. Insert each missing rule in a deterministic place — for `mach-lookup` allows, after any existing `mach-lookup` block; for `appleevent-send`, after existing `appleevent-send` lines; for `file-read*`/`file-write*`, near related filesystem rules.
2. Be applicable via `patch -p0 < <diff>` from the directory containing `profile.sb`.
3. NOT include any rule that is already present in the profile (the mode is "minimum patch", not "full regeneration").

`--suggest-sandbox-patch` MUST NOT actually edit the profile file. The user reviews and applies the diff manually (or via `hermes install` after editing `permissions.yaml` so the generator produces the same outcome).

#### Scenario: Patch only includes missing rules
- **GIVEN** `~/.hermes/profile.sb` already contains `(allow mach-lookup (global-name "com.apple.tccd"))` but is missing `(allow mach-lookup (global-name "com.apple.windowserver.active"))`
- **AND** doctor classifies `screen_recording` as `SANDBOX_BLOCKED`
- **WHEN** `hermes doctor --suggest-sandbox-patch` runs
- **THEN** the printed diff inserts only the WindowServer allow line, not the tccd line

### Requirement: Doctor refuses to nest sandbox-exec
If doctor itself is running inside an active `sandbox-exec` (detected by walking the parent-process chain for a `sandbox-exec` ancestor, or by the presence of the `SANDBOX_PROFILE` environment variable), it MUST NOT spawn a sandboxed pass. Instead, doctor MUST:
1. Log a warning: "doctor is already running under sandbox-exec; the sandboxed pass would compose two profiles and is suppressed. Rerun `hermes doctor` from outside the sandbox for the full 2×2 matrix."
2. Run only the baseline pass.
3. In `--json` output, set `sandbox.active = true` and `sandbox.differential = false` so consumers know the matrix was not computed.

#### Scenario: Nested invocation falls back to baseline-only
- **GIVEN** the current process tree includes a `sandbox-exec` ancestor
- **WHEN** `hermes doctor` runs
- **THEN** the report includes a single-pass section labeled "baseline only — running under sandbox"
- **AND** no sandboxed-pass subprocess is spawned

### Requirement: Doctor never auto-runs without explicit opt-in
`hermes doctor` MUST NOT be registered as a Claude `SessionStart` hook by default. Users who want pre-flight checks MAY opt in via a manifest field `hooks.doctor_on_session_start: true`, which `hermes install` SHALL translate into the appropriate `settings.json` hook entry. Opt-in invocations MUST use `hermes doctor --check --exit-zero` so a failing TCC state never blocks Claude startup.

#### Scenario: Default install does not add a doctor hook
- **WHEN** `hermes install` runs against a manifest that does not set `hooks.doctor_on_session_start`
- **THEN** `~/.claude/settings.json` after install contains no `SessionStart` entry referencing `hermes doctor`

### Requirement: Documentation of the re-grant ritual
The repo MUST document the "rebuild → re-grant" cycle in three locations, each scoped to its audience:
- `tools/probe-tcc/README.md` — for the maintainer who rebuilds the probe.
- This spec — as authoritative behaviour.
- The repo root `README.md` — for the end user, with a short troubleshooting section linking to `hermes doctor --fix`.

#### Scenario: Repo root README references the doctor
- **WHEN** the user reads the repo root `README.md`
- **THEN** it includes a section that mentions `hermes doctor` and explains that TCC permissions must be re-granted after a probe rebuild
