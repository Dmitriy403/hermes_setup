## Context

This change implements the three plugins deferred from `hermes-agent-installer` (v0.1.0) per that change's design Decision 19. It builds on the already-shipped framework — manifest schema, `hermes capture/install/verify`, the four-layer security model, and the two-repo split — none of which change here.

The relevant inherited decisions (in `hermes-agent-installer/design.md`) govern this work:
- **Decision 8** — bundled plugins live under `plugins/<name>/` in the tool repo, registered via the manifest.
- **Decision 10/11/12** — Telegram long-poll single process; voice via bundled `whisper.cpp` with cloud fallback off by default; backups via `restic` + `launchd` (not Time Machine).
- **Decision 13** — plugin OS permissions are documented, not auto-granted.
- **Decision 18** — plugin external dependencies fail soft (`{ok:false, error:"missing_dependency", needs, how_to_fix}`) and install lazily; `hermes doctor --plugin-deps` reports missing binaries.

## Goals / Non-Goals

**Goals:**
- Three working MCP-server/CLI plugins that register cleanly into the existing manifest and install via `hermes install`.
- Testable pure cores; live edges verified on a real-deps machine.

**Non-Goals:**
- Changing the installer, manifest schema, or security model (frozen at v0.1.0).
- A proactive Telegram agent loop (v1 is passive tool-only, per parent Decision; revisit later).

## Plugin engineering pattern (carried from v0.1.0)

Each plugin separates a **pure, testable core** from a **thin live edge** behind an injected boundary — exactly as `macos-control` (injectable `runner`) and `vision` (pure `build_*` + lazy SDK) did:

```
  telegram-bot → TelegramClient(Protocol): poll / get_file / send_*  (FakeClient in tests)
                 pure: allowlist check, ring buffer, update→message normalization
  voice        → Transcriber(Protocol): transcribe(path, lang)       (LocalWhisper / CloudWhisper)
                 pure: backend selection matrix, cmd construction, output parsing
  backups      → restic argv builder (pure) + Notifier(Protocol) for alerts
                 pure: exclude assembly, destination→repo string, launchd plist XML
```

The security/privacy/correctness logic (telegram allowlist, voice cloud-off guarantee, backups excludes) is the pure part and is exactly what must not break.

## Risks / Trade-offs

- **Live edges untestable in CI without deps** (Telegram token, `whisper.cpp`, `restic`). Mitigation: pure cores fully unit-tested; live round-trips deferred to a real-deps machine / the VM smoke. Per Decision 18.
- **Cross-plugin coupling**: `vision` analyzes Telegram photos, `voice` transcribes Telegram voice notes, `backups` alerts via `telegram-bot`. `telegram-bot` is the keystone — build it first so its tool contracts settle before the others lean on them.

## Decision: plugin install orchestration (form B)

`hermes install` writes MCP entries into `settings.json` but does **not** put
the plugin packages or their launchd jobs on the machine — so the registered
MCP commands (`hermes-telegram-bot`, `hermes-voice`, `hermes-macos-control`)
aren't on PATH, and the telegram/backup launchd jobs never load. This gap
affects v0.1.0's `macos-control` too. Decided (2026-05-29) to close it via
**form B**: keep plugins as separate packages (Decision 8), and have install
inject the ones the manifest registers into the tool's pipx venv.

**Mechanism** (path-deps via `file://` need absolute paths → not portable, so
extras are dev-sugar, not the target-machine path):
```
  hermes install / install.sh:
    for each plugin the manifest registers
      (mcp/<name>.yaml command == hermes-* , or manifest/backups.yaml present):
        pipx inject hermes <repo>/plugins/<dir>      # fallback: pip install <dir>
    for each plugin with a launchd job:
      write ~/Library/LaunchAgents/<label>.plist  +  launchctl bootstrap/load
```

**Plugin registry** (new, in the tool — e.g. `src/hermes/plugins_registry.py`):
maps plugin name → {package dir, console-script(s), launchd label + generator,
kind (mcp|skill|cli)}. The single source install consults to know what to
inject and which plists to load.

| plugin | dir | kind | console-script | launchd |
|--------|-----|------|----------------|---------|
| vision | manifest/skills/vision | skill | — | — |
| macos-control | plugins/macos_control | mcp | hermes-macos-control | — |
| telegram-bot | plugins/telegram_bot | mcp | hermes-telegram-bot | com.hermes.telegram-bot |
| voice | plugins/voice | mcp | hermes-voice | — |
| backups | plugins/backups | cli | hermes-backup | com.hermes.backup |

Lazy (Decision 18 spirit): only registered plugins are injected; nothing is
installed for plugins the manifest doesn't reference. Idempotent + dry-run via
the existing install `Mutator`. `hermes verify` grows a check that registered
plugins' console-scripts exist and their launchd jobs are loaded (closes §3.8).

Rejected: **A** (one package — contradicts Decision 8, fat venv) and **C**
(install infers everything with no explicit registry — more brittle than a
declared registry).

## Open Questions

1. Telegram: bundle `whisper.cpp` as a submodule vs `brew install whisper-cpp` (leaning brew, per parent Decision 11/Open Q6).
2. Backups: ship a default destination or force the user to configure (leaning unset, per parent Open Q8); auto `restic init` vs manual (leaning manual, parent Open Q9).
