#!/usr/bin/env bash
# Reproducible complete suite: private desktop, D-Bus, XDG files and GSettings.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "$0")/.." && pwd)
for executable in python magick dbus-run-session xvfb-run desktop-file-validate; do
  if ! command -v "$executable" >/dev/null; then
    echo "Missing test dependency: $executable" >&2
    exit 1
  fi
done
test_directory=$(mktemp -d -t wallpaper-cutter-suite-XXXXXXXX)
trap 'rm -rf -- "$test_directory"' EXIT
export XDG_CONFIG_HOME="$test_directory/config"
export XDG_STATE_HOME="$test_directory/state"
export XDG_DATA_HOME="$test_directory/data"
export XDG_CACHE_HOME="$test_directory/cache"
export XDG_RUNTIME_DIR="$test_directory/runtime"
export WALLPAPER_CUTTER_CONFIG_HOME="$XDG_CONFIG_HOME/wallpaper-cutter-linux"
export WALLPAPER_CUTTER_STATE_HOME="$XDG_STATE_HOME/wallpaper-cutter-linux"
mkdir -m 700 -- "$XDG_RUNTIME_DIR"
export GSETTINGS_BACKEND=memory
export GDK_BACKEND=x11
export GTK_A11Y=none
export GIO_USE_VFS=local
export GIO_USE_VOLUME_MONITOR=unix
export GTK_USE_PORTAL=0
export GDK_DEBUG=no-portals
export PYTHONDONTWRITEBYTECODE=1
export WALLPAPER_CUTTER_REQUIRE_GTK=1
cd -- "$project_dir"
test_command=(python -m unittest discover -s tests -v)
if [[ "${1:-}" == "--coverage" ]]; then
  shift
  coverage_directory="$project_dir/.test-coverage"
  mkdir -p -- "$coverage_directory"
  test_command=(python -m trace --count --missing --summary --ignore-dir /usr
                --coverdir "$coverage_directory" --module unittest discover -s tests -v)
fi
dbus-run-session -- xvfb-run -a -s '-screen 0 1600x1000x24' \
  "${test_command[@]}" "$@"
