#!/bin/sh
# The class Python sandbox.
#
# Every class skill runs on this one interpreter — a pinned CPython that uv
# downloads and manages — inside its own venv. The student's own Python is
# never used and never modified, even when it is a matching version.
#
# Run this once per machine; re-running is cheap and repairs a broken sandbox:
#
#     sh ensure-runtime.sh
#
# Its last line is `ENT164_PYTHON=...`: use exactly that interpreter for every
# other command. On macOS and Linux it is ~/.venvs/ent164-maker/bin/python.

set -eu

PY_VERSION=3.12.14                     # one pinned interpreter for the class
PILLOW_VERSION=12.3.0
PYYAML_VERSION=6.0.3
VENV="${ENT164_VENV:-$HOME/.venvs/ent164-maker}"
UV="${ENT164_UV:-$HOME/.local/bin/uv}"

say() { printf '  %s\n' "$1"; }
die() { printf 'error: %s\n' "$1" >&2; exit 1; }

if [ -z "$VENV" ]; then
  die "ENT164_VENV is empty"
fi

# 1. uv, the tool that installs and manages the pinned Python. It is a single
#    user-space binary (never a system package), and UV_NO_MODIFY_PATH tells
#    its installer to leave shell profiles alone — this script calls uv by
#    path, so nothing about the student's shell changes.
if [ ! -x "$UV" ]; then
  command -v curl >/dev/null 2>&1 || die "curl is needed to download uv"
  say "installing uv (the Python runtime manager) ..."
  tmp="${TMPDIR:-/tmp}/ent164-uv-install.$$"
  curl -LsSf -o "$tmp" https://astral.sh/uv/install.sh \
    || die "could not download uv — check your internet connection"
  if ! UV_INSTALL_DIR="$(dirname "$UV")" UV_NO_MODIFY_PATH=1 sh "$tmp"; then
    rm -f "$tmp"
    die "could not install uv"
  fi
  rm -f "$tmp"
  [ -x "$UV" ] || die "uv did not appear at $UV"
fi

# 2. The pinned interpreter. `only-managed` is the point: even when the
#    student already has a matching Python, the sandbox gets its own copy.
say "installing Python $PY_VERSION ..."
"$UV" python install "$PY_VERSION" --python-preference only-managed --quiet \
  || die "could not install Python $PY_VERSION — check your internet connection"

# 3. The venv. It is rebuilt whenever it is missing, damaged, or was made by
#    some other interpreter (an older version of this skill used the student's
#    Python for it).
PY="$VENV/bin/python"
MARK="$VENV/.ent164-python"
if [ -x "$PY" ] && [ -f "$MARK" ] && [ "$(cat "$MARK")" = "$PY_VERSION" ]; then
  : # already ours
else
  if [ -e "$VENV" ]; then
    say "replacing the venv at $VENV ..."
    rm -rf "$VENV"
  else
    say "creating the class venv at $VENV ..."
  fi
  mkdir -p "$(dirname "$VENV")"
  "$UV" venv --seed --python "$PY_VERSION" \
    --python-preference only-managed "$VENV" --quiet \
    || die "could not create the venv at $VENV"
  printf '%s\n' "$PY_VERSION" > "$MARK"
fi

# 4. The class packages, pinned as well. Re-running verifies rather than
#    reinstalls; the unpinned fallback covers a wheel disappearing for one
#    platform.
say "installing Pillow and PyYAML ..."
"$UV" pip install --quiet --python "$PY" \
  "Pillow==$PILLOW_VERSION" "PyYAML==$PYYAML_VERSION" \
  || "$UV" pip install --quiet --python "$PY" Pillow PyYAML

"$PY" -c 'import PIL, yaml' \
  || die "the sandbox at $VENV cannot import Pillow and PyYAML — re-run this script"

printf '\nsandbox : Python %s at %s\n' "$PY_VERSION" "$VENV"
printf 'ENT164_PYTHON=%s\n' "$PY"
