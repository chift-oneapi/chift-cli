#!/bin/sh
# chift CLI installer — downloads pre-built binaries from GitHub Releases
# Usage: curl -fsSL https://raw.githubusercontent.com/chift-oneapi/chift-cli/master/install.sh | sh
#
# Environment variables:
#   CHIFT_VERSION      - Pin to a specific release tag (default: latest)
#   CHIFT_INSTALL_DIR  - Override symlink directory (default: ~/.local/bin)
#   NO_COLOR           - Disable colored output
set -eu

# ── Helpers ──────────────────────────────────────────────────

BOLD=""
GREEN=""
RED=""
RESET=""
if [ -z "${NO_COLOR:-}" ] && [ -t 1 ]; then
    BOLD="\033[1m"
    GREEN="\033[32m"
    RED="\033[31m"
    RESET="\033[0m"
fi

info() { printf "${GREEN}info${RESET}  %s\n" "$1"; }
warn() { printf "${RED}error${RESET} %s\n" "$1" >&2; }
die()  { warn "$1"; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || return 1; }

# ── Parse flags ──────────────────────────────────────────────

MODIFY_PATH=1
for arg in "$@"; do
    case "$arg" in
        --help|-h)
            cat <<'EOF'
chift CLI installer

Downloads a pre-built binary from GitHub Releases and installs it.

Usage:
    curl -fsSL https://raw.githubusercontent.com/chift-oneapi/chift-cli/master/install.sh | sh

Options:
    --no-modify-path    Don't add the install directory to shell rc files

Environment variables:
    CHIFT_VERSION       Pin a release tag (e.g. v0.1.0). Default: latest
    CHIFT_INSTALL_DIR   Override symlink directory. Default: ~/.local/bin
    NO_COLOR            Disable colored output

After install:
    chift auth setup    Configure credentials
    chift --help        See all commands
EOF
            exit 0
            ;;
        --no-modify-path) MODIFY_PATH=0 ;;
    esac
done

# ── Configuration ────────────────────────────────────────────

[ -n "${HOME:-}" ] || die "HOME is not set. Cannot determine install location."

REPO="chift-oneapi/chift-cli"
VERSION="${CHIFT_VERSION:-latest}"
BIN_DIR="${CHIFT_INSTALL_DIR:-$HOME/.local/bin}"
LIB_DIR="$HOME/.local/lib/chift-cli"

# ── Detect platform ─────────────────────────────────────────

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

case "$OS" in
    darwin|linux) ;;
    *) die "Unsupported OS: $OS. Supported platforms: darwin (macOS), linux" ;;
esac

case "$ARCH" in
    x86_64|amd64)   ARCH="amd64" ;;
    aarch64|arm64)  ARCH="arm64" ;;
    *) die "Unsupported architecture: $ARCH. Supported: amd64 (x86_64), arm64 (aarch64)" ;;
esac

# ── Check dependencies ──────────────────────────────────────

need curl || die "curl is required but not found. Install it first."
need tar  || die "tar is required but not found. Install it first."

# ── Construct download URL ──────────────────────────────────

BINARY="chift-${OS}-${ARCH}"
TARBALL="${BINARY}.tar.gz"

if [ "$VERSION" = "latest" ]; then
    BASE_URL="https://github.com/${REPO}/releases/latest/download"
else
    BASE_URL="https://github.com/${REPO}/releases/download/${VERSION}"
fi

printf "\n"
info "Downloading chift CLI (${OS}/${ARCH})..."

# ── Download tarball and checksum ───────────────────────────

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

curl -fsSL "${BASE_URL}/${TARBALL}" -o "${TMPDIR}/${TARBALL}" \
    || die "Failed to download tarball. Check that a release exists with artifacts for ${OS}/${ARCH}."
curl -fsSL "${BASE_URL}/${TARBALL}.sha256" -o "${TMPDIR}/${TARBALL}.sha256" \
    || die "Failed to download checksum."

info "Download complete"

# ── Verify checksum ─────────────────────────────────────────

info "Verifying checksum..."
cd "$TMPDIR"
if [ "$OS" = "darwin" ]; then
    shasum -a 256 -c "${TARBALL}.sha256" >/dev/null 2>&1 \
        || die "Checksum verification failed! The downloaded archive may be corrupted."
else
    sha256sum -c "${TARBALL}.sha256" >/dev/null 2>&1 \
        || die "Checksum verification failed! The downloaded archive may be corrupted."
fi
info "Checksum verified"

# ── Extract to lib directory ────────────────────────────────

info "Installing to ${LIB_DIR}..."
rm -rf "$LIB_DIR"
mkdir -p "$LIB_DIR"
tar -xzf "${TMPDIR}/${TARBALL}" -C "$LIB_DIR" --strip-components=1
chmod +x "${LIB_DIR}/${BINARY}"

# ── Symlink to bin directory ────────────────────────────────

mkdir -p "$BIN_DIR"
ln -sf "${LIB_DIR}/${BINARY}" "${BIN_DIR}/chift"
info "Linked ${BIN_DIR}/chift -> ${LIB_DIR}/${BINARY}"

# ── PATH configuration ─────────────────────────────────────

PATH_LINE="export PATH=\"${BIN_DIR}:\$PATH\""

case ":${PATH}:" in
    *":${BIN_DIR}:"*)
        ;;
    *)
        if [ "$MODIFY_PATH" -eq 1 ]; then
            SHELL_NAME="$(basename "${SHELL:-/bin/sh}")"
            case "$SHELL_NAME" in
                zsh)  RC_FILE="$HOME/.zshrc" ;;
                bash) [ -f "$HOME/.bashrc" ] && RC_FILE="$HOME/.bashrc" || RC_FILE="$HOME/.bash_profile" ;;
                fish) RC_FILE="$HOME/.config/fish/config.fish" ;;
                *)    RC_FILE="$HOME/.profile" ;;
            esac

            if [ -f "$RC_FILE" ] && grep -qF "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
                :
            else
                mkdir -p "$(dirname "$RC_FILE")"
                if [ "$SHELL_NAME" = "fish" ]; then
                    printf '\n# Added by chift CLI installer\nfish_add_path "%s"\n' "$BIN_DIR" >> "$RC_FILE"
                else
                    printf '\n# Added by chift CLI installer\n%s\n' "$PATH_LINE" >> "$RC_FILE"
                fi
                info "Added ${BIN_DIR} to PATH in ${RC_FILE}"
            fi
            export PATH="${BIN_DIR}:$PATH"
        else
            printf "\n  %bAdd %s to your PATH:%b\n    %s\n\n" "$BOLD" "$BIN_DIR" "$RESET" "$PATH_LINE"
        fi
        ;;
esac

# ── Success ─────────────────────────────────────────────────

printf "\n"
info "chift CLI installed!"
printf "\n  %bGet started:%b\n" "$BOLD" "$RESET"
printf "    chift auth setup     # Configure credentials\n"
printf "    chift --help         # See all commands\n\n"
if [ -n "${RC_FILE:-}" ]; then
    printf "  Restart your shell or 'source %s' to pick up PATH changes.\n\n" "$RC_FILE"
fi
