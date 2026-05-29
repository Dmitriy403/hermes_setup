## ADDED Requirements

### Requirement: Probe is a standalone Swift binary in `tools/probe-tcc/`
The repo SHALL contain a Swift-based macOS TCC probe under `tools/probe-tcc/` whose build output `bin/hermes-probe-tcc` is committed to the repository. The probe MUST NOT be bundled into the Python `hermes` CLI; it is a separately versioned artifact governed by this capability. End users MUST NOT need to compile the probe themselves; the committed binary is the artifact they use.

#### Scenario: Repo ships a usable probe binary
- **WHEN** a user clones the repo at any tagged release
- **THEN** `bin/hermes-probe-tcc` exists and is executable
- **AND** running `bin/hermes-probe-tcc --json` produces a valid v1 probe report

### Requirement: Bundle identifier is `org.hermes.probe-tcc`
The probe binary's code-signing identifier MUST be `org.hermes.probe-tcc`. The same identifier MUST appear as `CFBundleIdentifier` in the embedded `Info.plist`. This identifier is the stable label TCC uses internally when displaying permission entries; it MUST NOT be changed casually.

#### Scenario: Identifier is consistent
- **WHEN** the user runs `codesign --display --verbose=4 bin/hermes-probe-tcc`
- **THEN** the output contains both `Identifier=org.hermes.probe-tcc` and `CFBundleIdentifier=org.hermes.probe-tcc` (via the embedded plist)

### Requirement: Info.plist is embedded via `__TEXT,__info_plist`
The probe is shipped as a single Mach-O binary (no `.app` bundle). The `Info.plist` MUST be embedded into the `__TEXT,__info_plist` section at link time using `swiftc -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker <plist>`. The embedded plist MUST contain at minimum:
- `CFBundleIdentifier`, `CFBundleExecutable`, `CFBundleName`, `CFBundleVersion`, `CFBundleShortVersionString`, `LSUIElement=true`
- `NSAppleEventsUsageDescription`
- `NSMicrophoneUsageDescription`
- `NSCameraUsageDescription`
- `NSDocumentsFolderUsageDescription`, `NSDesktopFolderUsageDescription`, `NSDownloadsFolderUsageDescription`
- `NSSpeechRecognitionUsageDescription`

The strings MUST be human-readable explanations of what the probe is doing. Missing any of the `NSXxxUsageDescription` keys causes macOS to `SIGKILL` the probe on first call to the corresponding API — this is a hard correctness requirement.

#### Scenario: Required Info.plist keys are present
- **WHEN** the build script produces `bin/hermes-probe-tcc`
- **THEN** all of `NSAppleEventsUsageDescription`, `NSMicrophoneUsageDescription`, `NSCameraUsageDescription`, `NSDocumentsFolderUsageDescription`, `NSDesktopFolderUsageDescription`, `NSDownloadsFolderUsageDescription`, `NSSpeechRecognitionUsageDescription` are present in the embedded plist

### Requirement: Ad-hoc signing (Scenario A)
For v1, the probe binary MUST be signed ad-hoc (`codesign --sign -`) with `--identifier org.hermes.probe-tcc`. No Apple Developer ID is required. The chosen scenario is documented in `design.md` (Decision: probe-tcc signing strategy) and the maintainer accepts that every rebuild produces a new `cdhash` and forces TCC grants to be re-issued.

A future migration to a paid Apple Developer Program account (Scenario C) MUST NOT require changes to the build script's CLI surface; the difference SHOULD reduce to a single `IDENTITY` environment variable that selects ad-hoc vs Developer ID.

#### Scenario: Signature is ad-hoc and identifier is stable
- **WHEN** `codesign --display --verbose=4 bin/hermes-probe-tcc` is run
- **THEN** the output contains `Signature=adhoc`
- **AND** `Identifier=org.hermes.probe-tcc`

### Requirement: Minimum macOS target is 13.0 (arm64)
The probe MUST be built with `-target arm64-apple-macosx13.0`. macOS versions below 13.0 are out of scope for v1. If the user has an Intel Mac, the build script MAY add a `-target x86_64-apple-macosx13.0` pass and `lipo` the two slices, but this is not required for v1.

#### Scenario: Loading on macOS 12 or earlier is unsupported
- **WHEN** a user attempts to run the probe on macOS 12.x
- **THEN** macOS may refuse to load the binary; `hermes doctor` MUST detect this case and print "macOS 13.0 or later required" rather than a generic crash

### Requirement: Build is reproducible enough for cdhash stability across reruns
The build script `tools/probe-tcc/build.sh` MUST produce a deterministic cdhash given identical sources, toolchain version, and SDK. To achieve this, the link step MUST pass `-Xlinker -no_uuid` and the build MUST NOT depend on wall-clock time or the working directory path. Bit-for-bit reproducibility across machines is a non-goal for v1 (different SDK patch versions are acceptable to vary cdhash); same-machine reruns from clean state MUST yield the same cdhash.

#### Scenario: Two consecutive clean builds produce the same cdhash
- **WHEN** the maintainer runs `./tools/probe-tcc/build.sh` twice in a row without editing any source
- **THEN** the cdhash reported by `codesign --display --verbose=4 bin/hermes-probe-tcc` is identical between the two builds

### Requirement: JSON output contract (v1)
The probe binary MUST emit a JSON document on stdout that conforms to schema `https://hermes/probe-tcc/v1`. The top-level shape SHALL include:
- `schema` — schema URI string
- `probe_version` — semver of the probe itself
- `probed_at` — ISO-8601 timestamp
- `self.{bundle_id, binary_path, cdhash, signature}`
- `responsible_process.{pid, path, bundle_id, name, chain[]}` where `chain[]` is the parent-process chain with one entry flagged `is_responsible: true`
- `sandbox.{active, profile_path}`
- `probes.{screen_recording, accessibility, automation, full_disk_access, microphone, camera, input_monitoring, files}` — each with `status`, `method`, optional `detail` / `fix_hint` / raw API error codes
- `summary.{total, granted, denied, partial, misaligned_bundle, extra_grants, blocked_by_sandbox}`
- `exit_code`

`status` values are an enum: `granted | denied | partial | blocked_by_sandbox | app_not_running | not_determined | unknown`. `partial` is only valid for categories with sub-elements (`automation.targets[]`, `files[]`).

#### Scenario: Output is a parseable v1 document
- **WHEN** `bin/hermes-probe-tcc --json --automation-targets=com.apple.finder --expect-files=~/Documents` is invoked
- **THEN** stdout is a single JSON object that parses successfully
- **AND** the object has `schema == "https://hermes/probe-tcc/v1"`

### Requirement: Silent probe APIs
Every probe MUST use the Apple-provided dry-check API for its category and MUST NOT trigger a TCC permission prompt during the default `--check` mode. Specifically:
- Screen Recording — `CGPreflightScreenCaptureAccess()`
- Accessibility — `AXIsProcessTrustedWithOptions([kAXTrustedCheckOptionPrompt: false])`
- Automation per app — `AEDeterminePermissionToAutomateTarget(target, typeWildCard, false)` with `AskUserIfNeeded = false`
- Full Disk Access — `open(/Library/Application Support/com.apple.TCC/TCC.db, O_RDONLY)`; success implies granted, `EPERM` implies denied
- Microphone — `AVCaptureDevice.authorizationStatus(for: .audio)`
- Camera — `AVCaptureDevice.authorizationStatus(for: .video)`
- Input Monitoring — `IOHIDCheckAccess(kIOHIDRequestTypeListenEvent)`
- Files (Documents/Desktop/Downloads) — `readdir(path)` against a marker file `.hermes-probe` placed by install

The probe MUST NEVER call `requestAccess` variants during `--check`. The `--warmup` mode is the only context in which prompting variants may be used, and even then only after the operator has explicitly chosen the mode.

#### Scenario: `--check` does not raise prompts
- **WHEN** `bin/hermes-probe-tcc --json` is run on a machine where Screen Recording has never been granted
- **THEN** no macOS permission dialog is shown
- **AND** the `screen_recording` probe returns `status: "denied"`

### Requirement: Responsible-process detection
The probe MUST report the responsible process the way TCC sees it. The detection MUST:
1. Walk the parent-pid chain from the probe's own pid via `getppid()`.
2. Identify the first ancestor whose executable path matches the pattern `*.app/Contents/MacOS/*`.
3. Resolve that ancestor's `CFBundleIdentifier` via `lsappinfo info -only bundleid` or an equivalent API.
4. Emit the full chain in `responsible_process.chain[]` with one entry flagged `is_responsible: true`.

If no ancestor is a `.app`, the probe MUST flag `responsible_process.is_responsible_unknown: true` so the doctor can render the case as "launchd or detached process".

#### Scenario: Terminal app is identified as responsible
- **WHEN** the probe is run from a shell launched by Ghostty
- **THEN** `responsible_process.bundle_id == "com.mitchellh.ghostty"`
- **AND** `chain[]` includes both the shell process and the Ghostty process

### Requirement: Probe is "dumb" — manifest is the doctor's concern
The probe MUST NOT read `manifest/`, `secrets.env`, or any project config file. All manifest-derived inputs flow through CLI arguments. Conversely, the probe MUST NOT annotate findings with "required-by-manifest" semantics; that classification belongs to `hermes doctor`.

#### Scenario: Probe runs without a manifest in sight
- **WHEN** the probe is invoked from a directory that contains no `manifest/` or `secrets.env`
- **THEN** the probe runs to completion and reports raw TCC state for every category it can probe

### Requirement: Self-test mode for sandbox-aware probing
The probe SHALL support a `--self-test` flag that re-runs the same probe matrix and is intended to be invoked through `sandbox-exec -f <profile> bin/hermes-probe-tcc --self-test --json`. In `--self-test` mode the probe MUST detect when an Apple API returns an error that is plausibly caused by Seatbelt suppression (e.g., `mach-lookup` denied, `kIOReturnNotPermitted`, `EPERM` on a file path the manifest had granted) and emit `status: "blocked_by_sandbox"` rather than `denied`.

#### Scenario: Self-test under sandbox surfaces blocked_by_sandbox
- **GIVEN** an `~/.hermes/profile.sb` that omits `(allow mach-lookup (global-name "com.apple.windowserver.active"))`
- **WHEN** `sandbox-exec -f ~/.hermes/profile.sb bin/hermes-probe-tcc --self-test --json` is executed
- **THEN** the `screen_recording` probe reports `status: "blocked_by_sandbox"`

### Requirement: Probes emit `required_sandbox_rules` when blocked
For every category whose status is `blocked_by_sandbox`, the probe MUST also emit a `required_sandbox_rules` array in its JSON entry. Each element is a string containing a Seatbelt S-expression (e.g., `(allow mach-lookup (global-name "com.apple.windowserver.active"))`) that would have to be added to the profile for the probe's underlying API call to reach TCC. The rules MUST cover both the per-category Apple service lookups and any file-path access the probe attempts (e.g., FDA via `open(TCC.db)` requires a `file-read*` rule). The probe MUST NOT guess; the emitted rules are baked into the probe's per-category implementation.

The probe MUST NOT emit `required_sandbox_rules` for categories whose status is anything other than `blocked_by_sandbox`. Doctor relies on the array's presence as the sole signal that a Seatbelt-derived remediation is appropriate.

#### Scenario: Blocked screen_recording lists its required mach-services
- **GIVEN** the probe runs under a Seatbelt profile that omits the WindowServer mach-lookup
- **WHEN** the probe writes its JSON output
- **THEN** `probes.screen_recording.status == "blocked_by_sandbox"`
- **AND** `probes.screen_recording.required_sandbox_rules` includes at least `(allow mach-lookup (global-name "com.apple.windowserver.active"))` and `(allow mach-lookup (global-name "com.apple.tccd"))`

#### Scenario: Non-blocked categories omit the field
- **GIVEN** the probe runs without an active sandbox (baseline pass)
- **WHEN** the probe writes its JSON output
- **THEN** no entry under `probes.*` contains the `required_sandbox_rules` field

### Requirement: Source-of-truth for category → sandbox rule mapping
The mapping from TCC category (and per-category sub-element like Automation target bundle id) to the required Seatbelt allow rules MUST live in a single file `tools/probe-tcc/sandbox-rules.yaml` checked into the repo. The probe source code (Swift) MUST read this file at build time (e.g., via `swiftc -D`-style code generation, or by embedding it as a string resource) so that probe and any other consumer share the same mapping. The Python install-time profile generator (under the `install` capability) MUST also read the same file. Drift between the two consumers is a defect.

#### Scenario: Both probe and install read the same source
- **GIVEN** `tools/probe-tcc/sandbox-rules.yaml` lists, for `screen_recording`, exactly the rules `(allow mach-lookup (global-name "com.apple.windowserver.active"))` and `(allow mach-lookup (global-name "com.apple.tccd"))`
- **WHEN** `hermes install` generates `~/.hermes/profile.sb` with Layer B enabled
- **AND** the probe emits `required_sandbox_rules` for a blocked `screen_recording`
- **THEN** the rules in the generated profile (for screen_recording) are identical to the rules the probe would emit if the profile were missing those rules

### Requirement: Build script invariants
`tools/probe-tcc/build.sh` MUST:
1. Compile all `Sources/*.swift` into `build/hermes-probe-tcc` via `swiftc` (no SwiftPM for v1).
2. Embed `Info.plist` via `-sectcreate __TEXT __info_plist`.
3. Run `codesign --force --sign - --identifier org.hermes.probe-tcc --entitlements entitlements.plist build/hermes-probe-tcc`.
4. Verify with `codesign --verify --verbose build/hermes-probe-tcc`.
5. Print the resulting `cdhash` to stdout so CI logs can record it.
6. Strip quarantine attributes via `xattr -d com.apple.quarantine` if present.

The script MUST exit non-zero if any step fails. The script MUST NOT install or move the binary to `bin/`; that step is a separate, committed action so the maintainer can review the diff before publishing.

#### Scenario: Build prints cdhash on success
- **WHEN** `./tools/probe-tcc/build.sh` runs to completion
- **THEN** the final line of stdout contains `cdhash: <64-hex-char string>`
