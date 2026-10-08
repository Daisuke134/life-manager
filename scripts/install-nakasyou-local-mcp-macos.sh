#!/usr/bin/env bash
# Install nakasyou/local-mcp on macOS for Life Manager development.
# REVIEW before running: this compiles third-party Rust code on your Mac.
# This script does not configure a public endpoint, start a background service,
# bypass approvals, or grant the AI unsandboxed execution rights.
set -euo pipefail

UPSTREAM="https://github.com/nakasyou/local-mcp.git"
REVISION="21025d048f54cc9f948c26ac42fa36183dc453c2"
SOURCE_DIR="$HOME/.local/share/life-manager/vendor/nakasyou-local-mcp"
BIN_DIR="$HOME/.local/bin"
EXECUTABLE="$BIN_DIR/life-manager-local-mcp"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer only supports macOS." >&2
  exit 2
fi

for dependency in git cargo xcode-select install cmp; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    echo "Missing $dependency; install the macOS Command Line Tools and Rust (rustup), then retry." >&2
    exit 2
  fi
done

if ! xcode-select -p >/dev/null 2>&1; then
  echo "Run 'xcode-select --install' and retry." >&2
  exit 2
fi

if [[ -e "$SOURCE_DIR" && ! -d "$SOURCE_DIR/.git" ]]; then
  echo "Refusing to overwrite a non-Git directory: $SOURCE_DIR" >&2
  exit 2
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  mkdir -p "$(dirname "$SOURCE_DIR")"
  git clone --filter=blob:none "$UPSTREAM" "$SOURCE_DIR"
fi

if [[ "$(git -C "$SOURCE_DIR" remote get-url origin)" != "$UPSTREAM" ]]; then
  echo "Refusing to use a source checkout with an unexpected origin." >&2
  exit 2
fi

if [[ -n "$(git -C "$SOURCE_DIR" status --porcelain)" ]]; then
  echo "Refusing to change a dirty source checkout: $SOURCE_DIR" >&2
  exit 2
fi

if [[ "$(git -C "$SOURCE_DIR" rev-parse HEAD)" != "$REVISION" ]]; then
  git -C "$SOURCE_DIR" checkout --detach "$REVISION"
fi

(
  cd "$SOURCE_DIR"
  cargo build --locked --release
)

BUILT="$SOURCE_DIR/target/release/local-mcp"
if [[ ! -x "$BUILT" ]]; then
  echo "Build did not produce the expected executable." >&2
  exit 1
fi

mkdir -p "$BIN_DIR"
if [[ -e "$EXECUTABLE" ]]; then
  if ! cmp -s "$BUILT" "$EXECUTABLE"; then
    echo "Refusing to overwrite an existing different executable: $EXECUTABLE" >&2
    exit 2
  fi
else
  install -m 0755 "$BUILT" "$EXECUTABLE"
fi

"$EXECUTABLE" --version
if ! printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | "$EXECUTABLE" mcp | grep -q '"serverInfo"'; then
  echo "MCP initialize smoke check failed." >&2
  exit 1
fi

cat <<INSTRUCTIONS

Build + local MCP initialize check completed.
Not yet connected to ChatGPT; this script has not configured remote access.

Next, in a separate Terminal:
  cd /Users/anicca/Projects/life-manager-main
  "$EXECUTABLE" start life-manager

Keep the approval UI running; leave permission mode at "ask".
For ChatGPT cloud, use a protected OpenAI Secure MCP Tunnel
with --mcp-command "$EXECUTABLE mcp" (see setup guide).
Do not use /permissions yolo or an unauthenticated public tunnel.
INSTRUCTIONS
