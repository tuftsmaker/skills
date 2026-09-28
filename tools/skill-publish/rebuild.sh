#!/usr/bin/env bash
#
# Rebuild index.json after editing any skill in this repo.
#
#   ./tools/skill-publish/rebuild.sh
#
# Then commit and push — that IS the publish step, because the registry is
# served straight from this repo by GitHub Pages. No upload, no server.
#
# Why this is needed: opencode only re-downloads a skill when its `version`
# changes, and the version is a hash of the skill's contents. Edit a file
# without rebuilding and the version stays put, so students keep the old copy.
# Rebuild and it changes by itself — you never bump a version by hand.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$(dirname "$HERE")")"
SKILLS="$REPO"

if [ ! -f "$SKILLS/breadboard-wiring/SKILL.md" ]; then
  echo "error: no skills at $SKILLS" >&2
  exit 1
fi

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "error: $PY not found. Set PYTHON=/path/to/python3 and retry." >&2
  exit 1
fi

# The sandbox bootstrap is deliberately duplicated into every skill (students
# download skills independently, so each must carry it), which means the
# copies must stay identical — a drifted copy is a different runtime.
for name in ensure-runtime.sh ensure-runtime.ps1; do
  ref="$SKILLS/breadboard-wiring/$name"
  [ -f "$ref" ] || continue
  for copy in "$SKILLS"/*/"$name"; do
    [ -f "$copy" ] || continue
    [ "$copy" = "$ref" ] && continue
    if ! cmp -s "$ref" "$copy"; then
      echo "error: $copy differs from $ref — keep the copies identical" >&2
      exit 1
    fi
  done
done

echo "==> rebuilding $SKILLS/index.json"
"$PY" "$HERE/build-index.py" --in-place --src "$SKILLS"

echo
echo "Next: git add -A && git commit && git push"
echo "Then verify the live copy before relying on it:"
echo "  curl -s https://tuftsmaker.github.io/skills/index.json"
