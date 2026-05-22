#!/usr/bin/env sh
set -eu

REPO="chift-oneapi/chift-cli"
BINARY="chift"

# ---------- helpers ----------

info()  { printf '\033[1;34m[chift]\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m[chift]\033[0m %s\n' "$*"; }
die()   { printf '\033[1;31m[chift]\033[0m error: %s\n' "$*" >&2; exit 1; }

need() {
    command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed."
}

# ---------- ensure uv ----------

ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        return
    fi
    info "uv not found — installing uv..."
    need curl
    curl -fsSL https://astral.sh/uv/install.sh | sh
    # uv installs to ~/.local/bin by default
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || die "uv installation failed. Add ~/.local/bin to your PATH and retry."
    ok "uv installed."
}

# ---------- fetch latest version ----------

latest_version() {
    need curl
    curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
        | grep '"tag_name"' \
        | sed 's/.*"tag_name": *"v\?\([^"]*\)".*/\1/'
}

# ---------- main ----------

main() {
    info "Installing chift-cli..."

    ensure_uv

    VERSION="${CHIFT_VERSION:-}"
    if [ -z "$VERSION" ]; then
        info "Fetching latest release..."
        VERSION="$(latest_version)"
        [ -n "$VERSION" ] || die "Could not determine latest version. Set CHIFT_VERSION to pin one."
        info "Latest version: $VERSION"
    fi

    WHEEL_NAME="chift_cli-${VERSION}-py3-none-any.whl"
    WHEEL_URL="https://github.com/${REPO}/releases/download/v${VERSION}/${WHEEL_NAME}"

    info "Downloading ${WHEEL_NAME}..."
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT

    curl -fsSL "$WHEEL_URL" -o "${TMP_DIR}/${WHEEL_NAME}" \
        || die "Download failed. Check https://github.com/${REPO}/releases for available versions."

    info "Installing via uv tool install..."
    uv tool install --force "${TMP_DIR}/${WHEEL_NAME}"

    UV_BIN_DIR="$(uv tool bin-dir 2>/dev/null || echo "$HOME/.local/bin")"

    ok "chift-cli $VERSION installed successfully."

    if ! command -v "$BINARY" >/dev/null 2>&1; then
        printf '\n'
        printf '  \033[1;33mAdd the following to your shell profile to use chift:\033[0m\n'
        printf '  export PATH="%s:$PATH"\n' "$UV_BIN_DIR"
        printf '\n'
    else
        ok "Run 'chift --help' to get started."
    fi
}

main "$@"
