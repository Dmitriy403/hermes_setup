# hermes_setup

A single installer that captures, installs, and verifies a Claude Code
("Hermes agent") environment — skills, plugins, MCP servers, settings, hooks,
keybindings, and `CLAUDE.md` — so the setup is portable and recoverable on a
fresh machine.

> Status: in development. The probe + `hermes doctor` subsystem (security
> capability checkup) is implemented; the capture/install/verify CLI and the
> bundled plugins are tracked in
> `openspec/changes/hermes-agent-installer/tasks.md`.

## Bootstrap a new machine

```sh
curl -fsSL https://gitcode.com/<user>/hermes_setup/raw/main/install.sh | bash
```

`install.sh` installs prerequisites (Homebrew + `python`/`git`/`node`/`pipx` on
macOS), the Claude Code CLI, clones this repo to `~/.hermes_setup`, installs the
`hermes` CLI via pipx (editable), helps you populate `secrets.env`, and runs
`hermes install`.

Environment overrides: `HERMES_REPO_URL`, `HERMES_REPO_REF`, `HERMES_HOME_DIR`,
`HERMES_SECRETS_FILE` (copy a prepared secrets file in), `HERMES_NONINTERACTIVE=1`
(unattended), `HERMES_SKIP_INSTALL=1` (stop before `hermes install`). Replace
`<user>` with the actual gitcode path before publishing.

> Linux is best-effort (the script branches on `uname`); Windows users should
> use WSL.

## `hermes doctor` — macOS TCC checkup

macOS gates Screen Recording, Accessibility, Automation, Full Disk Access,
Microphone, Camera, Input Monitoring, and Files & Folders behind TCC
(Transparency, Consent & Control). These permissions are granted to the
*responsible process* — usually your terminal app — not to Claude or to the
`hermes` CLI. When you switch terminals or rebuild the probe, macOS silently
stops recognizing the old grant and APIs start failing in confusing ways.

`hermes doctor` makes this legible:

```sh
hermes doctor              # read-only checkup (default)
hermes doctor --json       # machine-readable
hermes doctor --fix        # open the System Settings pane for each gap
hermes doctor --reset Accessibility   # tccutil reset a category
hermes doctor --mdm-profile           # emit a PPPC .mobileconfig
```

It reports, per category, whether the permission is granted and — if not —
*why*: a probe rebuild, a terminal swap, or a genuine revoke, each with a
one-click System Settings deep-link.

### Re-granting after a probe rebuild

The TCC probe binary (`bin/hermes-probe-tcc`) is **ad-hoc signed**. macOS binds
ad-hoc TCC permissions to the binary's exact `cdhash`, so **every rebuild of the
probe produces a new identity and macOS forgets the old grants.** This is
expected.

When it happens, `hermes doctor` detects it automatically and prints something
like:

```
Screen Recording   rebuild
    probe-tcc cdhash changed: aaaa… → bbbb… — re-grant Screen Recording:
    x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture
```

Run `hermes doctor --fix` and grant the listed categories again. This is a
one-time step per probe rebuild (which is rare — a few times a year).

> Building the probe yourself is a maintainer task; see
> [`tools/probe-tcc/README.md`](tools/probe-tcc/README.md). End users use the
> committed `bin/hermes-probe-tcc` and never need to rebuild it.

## Layout

```
bin/hermes-probe-tcc          committed probe binary (ad-hoc signed)
manifest/                     declarative description of the environment
  permissions.yaml            capability surface (filesystem/shell/network/mcp/tcc)
  probe-tcc.yaml              probe binary sidecar (expected cdhash)
src/hermes/                   the hermes CLI (Python)
  doctor/                     hermes doctor implementation
tools/probe-tcc/              probe binary sources + build/verify scripts
openspec/                     specs, design, and task tracking
```

## Development

```sh
pip install -e .
PYTHONPATH=src python3 -m hermes.doctor      # run doctor from source
./tools/probe-tcc/build.sh                   # rebuild the probe (maintainer)
./tools/probe-tcc/verify.sh                  # sanity-check the probe binary
```
