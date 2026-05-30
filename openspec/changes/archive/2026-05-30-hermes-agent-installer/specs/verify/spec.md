## ADDED Requirements

### Requirement: `hermes verify` reports drift between manifest and machine
The system SHALL provide a `hermes verify` command that compares the running user's Claude Code installation against `manifest/hermes.yaml` and reports any divergence.

#### Scenario: No drift on a freshly-installed machine
- **WHEN** `hermes verify` runs immediately after a successful `hermes install`
- **THEN** the command exits zero and prints "no drift"

#### Scenario: Drift is reported with actionable detail
- **WHEN** the user installs an extra skill manually that is not in the manifest
- **AND** runs `hermes verify`
- **THEN** the command exits non-zero
- **AND** stdout includes the extra skill's name under a section labeled "unexpected (present on machine, missing from manifest)"

### Requirement: Verify classifies each component as one of {match, missing, extra, modified}
For every component category the report MUST place each entry into exactly one of four classes: `match` (present and identical), `missing` (in manifest, absent on machine), `extra` (on machine, not in manifest), or `modified` (present on both but content differs).

#### Scenario: Modified setting is classified correctly
- **WHEN** the user edits `~/.claude/settings.json` to add a field not in the manifest
- **AND** runs `hermes verify`
- **THEN** the `settings` component is classified as `modified` with a unified diff in the output

### Requirement: Verify supports machine-readable output
`hermes verify --json` SHALL emit a JSON document with the same drift information, suitable for consumption by CI or other tools.

#### Scenario: JSON output is well-formed
- **WHEN** `hermes verify --json` runs
- **THEN** stdout is a single JSON object that parses successfully
- **AND** it contains a top-level `drift` array of `{component, name, status, detail}` objects

### Requirement: Verify checks `bin/hermes-probe-tcc` presence and cdhash
`hermes verify` MUST treat `bin/hermes-probe-tcc` as a manifest-tracked binary. The verifier MUST:
1. Confirm the file exists and is executable.
2. Run `codesign --display --verbose=4` (or an equivalent API call) and extract the binary's cdhash.
3. Compare the extracted cdhash against an `expected_cdhash` value stored in `manifest/probe-tcc.yaml` (a small sidecar manifest entry maintained by the build script).
4. Report `modified` if the cdhash differs and `missing` if the binary is absent.

The probe binary's signing identifier MUST also be checked against the value `org.hermes.probe-tcc` documented in the `probe-tcc` capability.

#### Scenario: Probe cdhash drift is reported
- **GIVEN** `manifest/probe-tcc.yaml` records `expected_cdhash: aaaa...`
- **WHEN** the binary on disk has cdhash `bbbb...` (e.g., the maintainer rebuilt without updating the manifest)
- **AND** `hermes verify` runs
- **THEN** the report classifies `probe-tcc` as `modified`
- **AND** stdout names both cdhash values for the user

### Requirement: Verify does NOT inspect TCC state
`hermes verify` MUST NOT run TCC probes. The two responsibilities are split: `verify` reports manifest-vs-machine drift for files, plugins, MCP servers, and the probe binary; `hermes doctor` reports TCC state for the responsible process. A user wanting a full health check is expected to run `hermes verify && hermes doctor`.

#### Scenario: Verify ignores TCC denials
- **GIVEN** the host terminal lacks Screen Recording permission
- **WHEN** `hermes verify` runs against an otherwise clean install
- **THEN** the command exits zero (no drift reported)
- **AND** TCC categories are not mentioned in the output
