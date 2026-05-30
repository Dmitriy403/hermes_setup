#!/usr/bin/env bash
# Hermes bootstrap — installs prerequisites, clones the repo, installs the
# `hermes` CLI, and hands off to `hermes install`.
#
#   curl -fsSL https://raw.githubusercontent.com/Dmitriy403/hermes_setup/main/install.sh | bash
#
# Environment overrides:
#   HERMES_REPO_URL        git URL to clone (default: the public GitHub repo)
#   HERMES_REPO_REF        branch/tag to checkout (default: main)
#   HERMES_HOME_DIR        clone destination (default: ~/.hermes_setup)
#   HERMES_CONFIG_URL      OPTIONAL git URL of a private hermes_config repo. If
#                          set, it is cloned to HERMES_CONFIG_DIR and `hermes
#                          install --manifest-dir <that dir>` runs against it.
#                          Unset → factory defaults from the tool's manifest/.
#   HERMES_CONFIG_DIR      where to clone the config repo (default: ~/hermes_config)
#   HERMES_SECRETS_FILE    path to a secrets.env to copy into the config dir
#                          (or the tool repo if HERMES_CONFIG_URL is unset)
#   HERMES_NONINTERACTIVE  =1 to skip all prompts (CI / unattended)
#   HERMES_SKIP_INSTALL    =1 to stop after setup, before `hermes install`

set -eu

HERMES_REPO_URL="${HERMES_REPO_URL:-https://github.com/Dmitriy403/hermes_setup.git}"
HERMES_REPO_REF="${HERMES_REPO_REF:-main}"
HERMES_HOME_DIR="${HERMES_HOME_DIR:-$HOME/.hermes_setup}"
HERMES_CONFIG_DIR="${HERMES_CONFIG_DIR:-$HOME/hermes_config}"
HERMES_NONINTERACTIVE="${HERMES_NONINTERACTIVE:-0}"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

OS="$(uname -s)"

# ---- 1. prerequisites ----

install_prereqs_macos() {
    if ! have brew; then
        log "Homebrew not found — installing"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Make brew available in this shell (Apple Silicon vs Intel).
        if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
        if [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi
    fi
    log "Installing prerequisites via Homebrew"
    for pkg in python git node pipx; do
        if ! brew list "$pkg" >/dev/null 2>&1; then
            brew install "$pkg"
        fi
    done
    pipx ensurepath >/dev/null 2>&1 || true
}

install_prereqs_linux() {
    log "Linux detected — checking prerequisites"
    for tool in python3 git node; do
        have "$tool" || warn "missing '$tool' — install it via your package manager"
    done
    if ! have pipx; then
        if have apt-get; then sudo apt-get update && sudo apt-get install -y pipx
        elif have dnf; then sudo dnf install -y pipx
        else warn "install 'pipx' manually (https://pipx.pypa.io)"; fi
    fi
    have pipx && pipx ensurepath >/dev/null 2>&1 || true
}

case "$OS" in
    Darwin) install_prereqs_macos ;;
    Linux)  install_prereqs_linux ;;
    *)      die "unsupported OS: $OS (macOS primary, Linux best-effort; Windows → use WSL)" ;;
esac

# ---- 2. claude CLI ----

if ! have claude; then
    if have npm; then
        log "Installing the Claude Code CLI"
        npm install -g @anthropic-ai/claude-code || warn "claude CLI install failed — install it manually"
    else
        warn "npm not found — install the Claude Code CLI manually, then re-run"
    fi
else
    log "claude CLI present: $(claude --version 2>/dev/null | head -n1 || echo unknown)"
fi

# ---- 3. clone repo + install hermes ----

if [ -d "$HERMES_HOME_DIR/.git" ]; then
    log "Updating existing checkout at $HERMES_HOME_DIR"
    # The clone is a tool-installer mirror, not a dev branch — force it to
    # match origin. `pull --ff-only` would silently fail here for two reasons:
    #   1. `--depth 1` clones create graft points; subsequent shallow fetches
    #      can leave local and origin with no visible common ancestor, so git
    #      reports the branches as "diverged" even when they are linear.
    #   2. Any local edit would block a fast-forward.
    # `fetch + reset --hard` sidesteps both and is the right semantics for an
    # installer that owns this directory.
    git -C "$HERMES_HOME_DIR" fetch --depth 1 origin "$HERMES_REPO_REF"
    git -C "$HERMES_HOME_DIR" reset --hard "origin/$HERMES_REPO_REF"
else
    log "Cloning $HERMES_REPO_URL → $HERMES_HOME_DIR"
    git clone --depth 1 --branch "$HERMES_REPO_REF" "$HERMES_REPO_URL" "$HERMES_HOME_DIR"
fi

# PEP 668: Homebrew Python is externally managed, so use pipx (NOT pip install -e).
log "Installing the hermes CLI via pipx (editable)"
pipx install --editable "$HERMES_HOME_DIR" --force

# ---- 3.5. optional private config repo ----
#
# If HERMES_CONFIG_URL is set, clone it and install reads its manifest+secrets.
# Otherwise install runs against the tool's factory manifest (no secrets needed).

MANIFEST_ROOT=""   # empty → factory; non-empty → `--manifest-dir $MANIFEST_ROOT`
if [ -n "${HERMES_CONFIG_URL:-}" ]; then
    if [ -d "$HERMES_CONFIG_DIR/.git" ]; then
        log "Updating existing config at $HERMES_CONFIG_DIR"
        # Config repo is user-owned (may have local commits); ff-only respects
        # that. Surface failures rather than silently using a stale checkout.
        git -C "$HERMES_CONFIG_DIR" pull --ff-only \
            || warn "could not fast-forward $HERMES_CONFIG_DIR — install will use the current checkout. Reconcile manually if needed."
    else
        log "Cloning $HERMES_CONFIG_URL → $HERMES_CONFIG_DIR"
        git clone --depth 1 "$HERMES_CONFIG_URL" "$HERMES_CONFIG_DIR"
    fi
    MANIFEST_ROOT="$HERMES_CONFIG_DIR"
    log "Using private config root: $MANIFEST_ROOT"
fi

# ---- 4. secrets ----
#
# Secrets land next to the manifest the install will read: in the config repo
# when one was cloned, else in the tool repo (factory plugins need no secrets).

if [ -n "$MANIFEST_ROOT" ]; then
    SECRETS_DST="$MANIFEST_ROOT/secrets.env"
    SECRETS_EXAMPLE="$MANIFEST_ROOT/secrets.env.example"
else
    SECRETS_DST="$HERMES_HOME_DIR/secrets.env"
    SECRETS_EXAMPLE="$HERMES_HOME_DIR/secrets.env.example"
fi

if [ -n "${HERMES_SECRETS_FILE:-}" ]; then
    log "Copying secrets from $HERMES_SECRETS_FILE → $SECRETS_DST"
    cp "$HERMES_SECRETS_FILE" "$SECRETS_DST"
    chmod 600 "$SECRETS_DST"
elif [ ! -f "$SECRETS_DST" ]; then
    if [ -f "$SECRETS_EXAMPLE" ]; then
        cp "$SECRETS_EXAMPLE" "$SECRETS_DST"
        chmod 600 "$SECRETS_DST"
    fi
    if [ -z "$MANIFEST_ROOT" ]; then
        log "Factory install — no secrets required for the default plugins."
    elif [ "$HERMES_NONINTERACTIVE" = "1" ]; then
        warn "secrets.env not populated (non-interactive). Fill $SECRETS_DST before 'hermes install'."
    else
        warn "Populate $SECRETS_DST with real values, then run 'hermes install'."
        printf 'Open it now? [y/N] '
        read -r ans || ans=n
        case "$ans" in
            y|Y) "${EDITOR:-vi}" "$SECRETS_DST" ;;
        esac
    fi
fi

# ---- 5. hand off to hermes install ----

run_hermes_install() {
    if [ -n "$MANIFEST_ROOT" ]; then
        hermes install --manifest-dir "$MANIFEST_ROOT"
    else
        hermes install
    fi
}

if [ "${HERMES_SKIP_INSTALL:-0}" = "1" ]; then
    log "Setup complete. Run 'hermes install' when ready."
    exit 0
fi

if [ "$HERMES_NONINTERACTIVE" = "1" ]; then
    log "Running 'hermes install'"
    run_hermes_install
else
    log "Setup complete."
    printf 'Run "hermes install" now? [y/N] '
    read -r ans || ans=n
    case "$ans" in
        y|Y) run_hermes_install ;;
        *)   log "Skipped. Run 'hermes install' when ready." ;;
    esac
fi
