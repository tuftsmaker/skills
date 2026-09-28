# Working in the class-skills repo

Served at <https://tuftsmaker.github.io/skills/> and consumed by opencode
through its `skills.urls`. The skills are student-facing; the working agreement
lives here so it lives with them.

## Publishing: one source, generated index

- `maker/`, `maker-tasks/` and `box/` are the source of truth. `index.json` is
  generated — never hand-edit it.
- After any skill edit: `./tools/skill-publish/rebuild.sh`, then commit and
  push. opencode re-downloads a skill only when its content-based `version`
  changes; editing without rebuilding means students silently keep the old
  copy.
- The pre-commit hook (`scripts/install-git-hooks.sh` once per clone) runs the
  rebuild when skill content is staged. `git commit --no-verify` bypasses it.
- After pushing, curl the live `index.json` and confirm every listed file
  returns 200 (script in README.md). Failures are silent: a 404 means the
  skill never appears on student machines.

## The pinned Python sandbox

- Every skill carries `ensure-runtime.sh` and `ensure-runtime.ps1`; the copies
  must stay byte-identical (`rebuild.sh` checks, CI runs both platforms). The
  first skill a student runs installs uv, has it download the pinned CPython
  (exact patch) and builds `~/.venvs/ent164-maker` with pinned Pillow and
  PyYAML.
- The ensure scripts are the only place versions live; bump every copy
  together when bumping.
- Keep `ensure-runtime.ps1` **pure ASCII**: Windows PowerShell 5.1 reads a
  BOM-less `.ps1` as ANSI, so a UTF-8 em dash becomes a smart quote and the
  parser dies with a confusing "missing the terminator" error.
- Nothing installs into or falls back to a student's own Python, even a
  matching one. `box/env.py` only locates the sandbox.

## Conventions that travel with the skills

- Skills are **student-facing**: no repo build tooling and no teacher-only
  notes inside `SKILL.md` — those belong here or in `tools/`.
- `.nojekyll` is load-bearing (underscore files, `SKILL.md` served verbatim).
- `tools/skill-publish/` is the publisher and the copy-sync check;
  `tools/ci/` holds test fixtures only. Both are excluded from the registry by
  `build-index.py`.
- History: extracted from `tuftsmaker/ENT-164` (September 2026) with
  `git filter-branch --prune-empty --subdirectory-filter skills/`, so the
  commits before that are the skills' own.
