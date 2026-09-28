#!/usr/bin/env bash
# Point this clone at the tracked git hooks in scripts/git-hooks/.
#
# Git does not version .git/hooks, so the hook lives in scripts/git-hooks/ and
# core.hooksPath points at it. That also means the hooks travel with the repo
# and cannot drift from the scripts they call.
#
# Run once per clone:
#     scripts/install-git-hooks.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS="$ROOT/scripts/git-hooks"

if [[ ! -d "$HOOKS" ]]; then
  echo "ERROR: $HOOKS not found" >&2
  exit 1
fi

chmod +x "$HOOKS"/* 2>/dev/null || true
git -C "$ROOT" config core.hooksPath scripts/git-hooks

echo "git hooks installed from scripts/git-hooks:"
for h in "$HOOKS"/*; do
  printf '  %s\n' "$(basename "$h")"
done
echo
echo "The pre-commit hook rebuilds index.json when skill content is staged."
echo "Bypass a single commit with: git commit --no-verify"
