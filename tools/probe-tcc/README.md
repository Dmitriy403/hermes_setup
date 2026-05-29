# tools/probe-tcc

Tiny Swift CLI that probes macOS TCC permissions silently and emits JSON.
Used by `hermes doctor`.

## Build

```sh
./build.sh
```

This produces `build/hermes-probe-tcc` — a single Mach-O binary with embedded
`Info.plist`, ad-hoc signed. After building, commit the resulting binary into
`bin/hermes-probe-tcc` at the repo root (separate step so the maintainer reviews
the diff before publishing).

## Signing model

**Scenario A** (committed 2026-05-25): ad-hoc signing only. No Apple Developer
account is required.

Every rebuild produces a new cdhash. macOS TCC binds permissions for ad-hoc
signed binaries to the literal cdhash, so TCC treats each rebuild as a new
application and requires permissions to be re-granted.

`hermes doctor` detects this automatically by comparing the current cdhash
against the one recorded in `~/.hermes/probe-cache.json` and prints deep-link
URLs into System Settings so the re-grant flow is one click away.

## Adding a new TCC category

1. Author a `<Category>.swift` probe under `Sources/`.
2. If Apple requires a Usage Description for this category, add the
   corresponding `NSXxxUsageDescription` key to `Info.plist` **before** the
   first run. Otherwise macOS will `SIGKILL` the probe on the first call.
3. Add the category enum case in `ProbeResult` and human formatter
   (`Output.swift`).
4. Rebuild (`./build.sh`), commit the new `bin/hermes-probe-tcc`, then run
   `hermes doctor` once to re-grant permissions.

## Why not a `.app` bundle?

A single Mach-O with the `__TEXT,__info_plist` section is enough for TCC and
avoids the bundle directory overhead. Visit again if we later need
`Helper.app`-style features (XPC, LaunchAgent).
