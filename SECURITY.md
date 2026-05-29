# Security model

Hermes captures, installs, and verifies a Claude Code environment. This
document explains the secret-handling and the layered permission model so you
can reason about what the agent can and cannot do.

## Secrets: what is and isn't captured

`hermes capture` reads `~/.claude/` and writes a manifest, but **never** stores
secrets or ephemeral state.

- **Redaction.** Secret-shaped values (API keys, tokens — `sk-…`, `ghp_…`,
  `AKIA…`, Telegram tokens, and any high-entropy value in a `*_KEY` / `*_TOKEN`
  / `*_SECRET` field) are replaced with `${VAR}` placeholders. The variable
  names are written to `secrets.env.example`. Extend the patterns in
  `manifest/.redact.yaml`.
- **Secrets live only in `secrets.env`** (gitignored). `hermes install`
  resolves `${VAR}` placeholders from the environment first, then `secrets.env`,
  and **fails fast before writing anything** if a required variable is missing.
- **Never captured:** conversation history, sessions, telemetry, caches,
  `settings.local.json`, and everything else under the excluded paths
  (`src/hermes/paths.py: EXCLUDED_CLAUDE_NAMES`).
- **Review the diff before committing.** Redaction is defense-in-depth, not a
  guarantee. If a non-standard secret shape slips through, add a pattern to
  `manifest/.redact.yaml` and re-capture.

### Rotating a leaked secret

If a secret is committed by mistake: rotate it at the source (regenerate the
key/token), purge it from git history, and add its shape to
`manifest/.redact.yaml` so capture catches it next time.

## Layered permissions

The agent's capability surface is declared in `manifest/permissions.yaml` and
enforced in up to three layers.

### Layer A — `PreToolUse` hook (always on)

`hermes install` registers a `PreToolUse` hook
(`hermes.hooks.pretooluse_enforce`) that evaluates every `Write`, `Edit`,
`Read`, `Bash`, `WebFetch`, and `mcp__*` call against `permissions.yaml`
**before** it reaches the OS, returning allow / ask / deny.

- `filesystem.forbidden` paths (`~/.ssh`, `*.pem`, `**/secrets.env`, keychains,
  TCC.db, …) are denied for read and write.
- `shell.deny` (`sudo`, `rm -rf /`, …) is denied; `shell.ask` prompts;
  everything else is allowed (v1 is allow-by-default + denylist).
- `network.domains` is the WebFetch allowlist; unlisted domains follow
  `network.default` (`ask` in v1).
- `mcp.disabled` servers are denied; if `mcp.enabled` is non-empty, unlisted
  servers prompt.

Run `hermes capabilities` to see the effective policy.

### Layer B — `sandbox-exec` profile (opt-in)

Enable with `security.layer_b.enabled: true`. `hermes install` then generates
`~/.hermes/profile.sb` from the same `permissions.yaml`, and `hermes run`
launches Claude under `sandbox-exec -f ~/.hermes/profile.sb` for kernel-level
filesystem and Apple-Events enforcement. Network filtering stays coarse
(port-level); domain rules remain Layer A's job.

Seatbelt denials look identical to TCC denials at the API level, so debugging
is opaque without help — `hermes doctor` runs a differential probe and a 2×2
matrix, and `hermes doctor --suggest-sandbox-patch` prints the missing rules.

### Layer C — VM mode (future)

Running Claude in a Lima/tart VM with only `~/projects/` mounted is out of
scope for v1.

## macOS TCC and the responsible process

macOS gates Screen Recording, Accessibility, Automation, etc. behind TCC, and
grants them to the **responsible process** — usually your terminal app, not
Claude or the `hermes` CLI. Switching terminals silently invalidates grants.
`hermes doctor` makes this legible and (because the TCC probe binary is ad-hoc
signed) detects when a probe rebuild requires re-granting. See the repo
[`README.md`](README.md) for the `hermes doctor --fix` flow.

`hermes verify` reports manifest-vs-machine drift but does **not** inspect TCC;
run `hermes verify && hermes doctor` for a full health check.
