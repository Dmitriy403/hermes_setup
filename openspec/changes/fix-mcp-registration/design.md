## Context

`hermes install` currently materializes MCP servers by merging them into `~/.claude/settings.json` under `mcpServers` (`installer.py:_build_settings`, ~lines 219-224). The installer docstring records this as a deliberate v1 decision: "MCP servers are written into settings.json's `mcpServers` map for v1 — avoids a hard dependency on `claude mcp add`."

That decision rests on a false premise. Claude Code loads MCP servers from `~/.claude.json` (the store `claude mcp add` writes, with user / project / local scopes) and from project `.mcp.json` — not from `settings.json`. Confirmed live: `claude mcp list` listed only `mempalace` (configured separately in `~/.claude.json`); none of hermes's settings.json servers (`telegram-bot`, `macos-control`, `voice`) appeared. `claude mcp add -s local telegram-bot ...` made it `✓ Connected` instantly.

`hermes verify` masks this: `_verify_plugin_packages` reports a server as `match` when its plugin package is present, never checking whether Claude Code can actually load it. So the system reports green while every hermes MCP server is dead.

Manifest MCP entries carry `name`, `command`, `args`, `env` (see `Manifest.mcp_servers`). The Layer A hooks now live in `settings.json` (PreToolUse/SessionStart/Stop) and must not be disturbed.

## Goals / Non-Goals

**Goals:**
- Manifest MCP servers actually load in Claude Code after `hermes install`.
- Registration is idempotent and respects `--dry-run` / `--confirm`.
- Migrate existing machines off the dead `settings.json` `mcpServers` map.
- `hermes verify` reports declared-but-unloaded servers as drift, not `match`.
- A regression test pins the bug class so it can't silently return.

**Non-Goals:**
- Changing the telegram-bot poller architecture or adding autonomous replies (separate concern).
- Managing MCP servers hermes did not install (e.g. user's own `mempalace`, claude.ai connectors).
- Choosing per-server scope policy beyond a sensible default (see Open Questions).

## Decisions

**D1 — Register via `claude mcp add` (CLI), not by hand-editing `~/.claude.json`.**
Rationale: `~/.claude.json` is large, shared, and its schema is owned by Claude Code; hand-editing risks corrupting unrelated state (projects, history, auth). `claude mcp add` is the supported, forward-compatible interface. *Alternative considered:* write a project `.mcp.json` — simpler and committable, but `.mcp.json` is shared/version-controlled and would put secrets (telegram token) in the repo; rejected as the default for secret-bearing servers. We may still emit `.mcp.json` for secretless servers (Open Question).

**D2 — Per-server scope: `user` default, polling servers → `local` (RESOLVED with user).**
Decided via explicit user choice ("Per-server"). Non-polling servers (macos-control, voice) register at `user` scope so they work in every session. Polling servers (telegram-bot, which long-polls getUpdates) set `scope: local` in their manifest sidecar so only one poller runs per project session — `user` scope would spawn a poller per session and hit Telegram's 409. The launchd signal can't identify pollers (telegram-bot has no launchd job since commit 9a09925), so the poller→local choice is an explicit per-server manifest override, not auto-derived. *Alternatives rejected:* uniform `user` (telegram 409 under concurrent sessions); uniform `local` (macos/voice wouldn't work outside one project dir); `project`/.mcp.json (commits the telegram token to a repo). Implemented: `McpServer.scope` override, default `user`.

**D3 — Idempotency by query-before-add.**
Run `claude mcp get <name>` (or parse `claude mcp list`) before adding; skip if already registered with matching command/env. This keeps re-runs clean and lets `--dry-run` report "would add" vs "already present".

**D4 — Migration: strip `mcpServers` from `settings.json` during install.**
`_build_settings` stops injecting `mcpServers`; additionally, if an existing `settings.json` already has a hermes-written `mcpServers` map, install removes it (through the existing `Mutator`, so `--confirm` shows the diff and `--dry-run` only logs). Layer A hook keys are preserved.

**D5 — verify gains a real MCP-load check.**
New verifier queries `claude mcp list`/`get` for each manifest server and reports drift when absent from a Claude-Code-read location. `_verify_settings` stops expecting `mcpServers`. A server found only under `settings.json` counts as NOT registered.

**D6 — Fail-soft when `claude` CLI is absent.**
The v1 decision's one real merit was avoiding a hard `claude` dependency. Preserve it as fail-soft: if `which("claude")` is None, skip MCP registration, surface the exact `claude mcp add` commands to run manually, and finish the rest of the install (consistent with the existing fail-soft posture for brew deps).

## Risks / Trade-offs

- **[Coupling to `claude mcp` CLI surface]** → CLI flags could change across Claude Code versions. Mitigation: isolate all CLI calls behind one small adapter module; cover with the regression test; fail-soft on non-zero exit with the raw stderr surfaced.
- **[`claude mcp add` mutates global `~/.claude.json`]** → a bug could touch unrelated state. Mitigation: only ever call `add`/`get`/`list`/`remove` for hermes-owned server names; never write the file directly.
- **[local scope tied to a project dir]** → server only loads in sessions opened in that project. Mitigation: document; let manifest override scope; this is the intended trade-off per D2.
- **[Migration on a machine the user hand-edited]** → stripping `mcpServers` could remove an entry the user added themselves. Mitigation: only strip entries whose names match manifest-declared servers; leave foreign keys; `--confirm` shows the diff.
- **[Dead config elsewhere]** → `macos-control` and `voice` were never actually loaded; enabling them may surface latent runtime issues (TCC prompts, missing deps). Mitigation: out of scope here, but flag in install output.

## Migration Plan

1. Ship installer change (stop writing `mcpServers`; add registration step; add migration strip).
2. On next `hermes install`, existing machines: stale `settings.json.mcpServers` removed, servers re-registered via `claude mcp add` (local scope). Idempotent, so safe to re-run.
3. `hermes verify` now flags any server that didn't register, giving users a clear signal.
4. Rollback: revert installer commit; old behavior writes `mcpServers` back (harmless dead config). No data migration to undo since `~/.claude.json` entries are removable via `claude mcp remove`.

## Open Questions

- Should secretless servers (`macos-control`, `voice`) optionally go to a committable `.mcp.json` while secret-bearing ones (`telegram-bot`) stay `local`-scope? Or keep everything uniform on `claude mcp add -s local` for simplicity? (Leaning uniform `local` for v1.)
- Should `verify`'s MCP check spawn `claude mcp list` (slow, does a health probe) or just check config-file presence (fast, no probe)? Presence check is cheaper and sufficient to catch the bug class; health probe is more truthful. (Leaning presence check + optional `--probe`.)
- How to detect "hermes-written" `mcpServers` for migration vs a user's own entry — match by manifest server names only, or also stamp a marker? (Leaning name-match against manifest.)
