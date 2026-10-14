#!/usr/bin/env bash
# Compatibility launcher for the cross-platform per-user installer.
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
if command -v python3 >/dev/null; then
  exec python3 "$source_dir/install.py"
fi
exec python "$source_dir/install.py"
