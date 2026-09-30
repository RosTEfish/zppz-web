#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRATE="$ROOT/tools/zppz-chart-validate"
OUT_DIR="${1:-$ROOT/backend/bin}"
BIN_NAME="zppz-chart-validate"

if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo is required to build $BIN_NAME" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
cargo build --release --manifest-path "$CRATE/Cargo.toml"
install -m 755 "$CRATE/target/release/$BIN_NAME" "$OUT_DIR/$BIN_NAME"
echo "Installed $OUT_DIR/$BIN_NAME"
