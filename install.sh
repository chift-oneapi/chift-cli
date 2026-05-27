#!/usr/bin/env sh
set -eu

REPO="chift-oneapi/chift-cli"
BINARY="chift"
INSTALL_DIR="${CHIFT_INSTALL_DIR:-$HOME/.local/bin}"

# ---------- helpers ----------

info() { printf '\033[1;34m[chift]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[chift]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[chift]\033[0m error: %s\n' "$*" >&2; exit 1; }

need() {
    command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed."
}

# ---------- detect platform ----------

detect_target() {
    OS="$(uname -s)"
    ARCH="$(uname -m)"

    case "$OS" in
        Linux)
            case "$ARCH" in
                x86_64) echo "linux-x86_64" ;;
                *) die "Unsupported Linux architecture: $ARCH" ;;
            esac
            ;;
        Darwin)
            case "$ARCH" in
                x86_64) echo "darwin-x86_64" ;;
                arm64)  echo "darwin-arm64" ;;
                *) die "Unsupported macOS architecture: $ARCH" ;;
            esac
            ;;
        *) die "Unsupported OS: $OS" ;;
    esac
}

# ---------- fetch latest version ----------

latest_version() {
    curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
        | grep '"tag_name"' \
        | sed 's/.*"tag_name": *"//; s/^v//; s/".*//'
}

# ---------- main ----------

main() {
    need curl

    info "Installing chift-cli..."

    TARGET="$(detect_target)"
    info "Detected platform: $TARGET"

    VERSION="${CHIFT_VERSION:-}"
    if [ -z "$VERSION" ]; then
        info "Fetching latest release..."
        VERSION="$(latest_version)"
        [ -n "$VERSION" ] || die "Could not determine latest version. Set CHIFT_VERSION to pin one."
        info "Latest version: $VERSION"
    fi

    BINARY_NAME="chift-${TARGET}"
    BINARY_URL="https://github.com/${REPO}/releases/download/v${VERSION}/${BINARY_NAME}"

    info "Downloading ${BINARY_NAME}..."
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT

    curl -fsSL "$BINARY_URL" -o "${TMP_DIR}/${BINARY}" \
        || die "Download failed. Check https://github.com/${REPO}/releases for available versions."

    chmod +x "${TMP_DIR}/${BINARY}"

    mkdir -p "$INSTALL_DIR"
    mv "${TMP_DIR}/${BINARY}" "${INSTALL_DIR}/${BINARY}"

    ok "chift-cli $VERSION installed to ${INSTALL_DIR}/${BINARY}."

    if ! command -v "$BINARY" >/dev/null 2>&1; then
        printf '\n'
        printf '  \033[1;33mAdd the following to your shell profile:\033[0m\n'
        printf '  export PATH="%s:$PATH"\n' "$INSTALL_DIR"
        printf '\n'
    else
        ok "Run 'chift --help' to get started."
    fi
}

main "$@"
