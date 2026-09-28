# TuftsMaker class skills

The ENT-164 *Intro to Making* skills for [opencode](https://opencode.ai) —
breadboard wiring diagrams, laser-ready files, and box/birdhouse generators
that students run on their own machines.

Served by GitHub Pages and consumed through opencode's `skills.urls`:

```
https://tuftsmaker.github.io/skills/
```

Students add that URL to opencode once (the class setup guide and the
`add-class-tools` handout tell them how), then pick up changes automatically.

## What's here

| skill | what it does | packages |
| --- | --- | --- |
| `breadboard-wiring` | breadboard wiring diagrams for the Freenove ESP32-WROVER / FNK0046 kit (SVG + PNG) | PyYAML |
| `laser-ready` | turns an Onshape DXF into the pure-red hairline SVG the Nolop laser reads; cuts finger joints | stdlib only |
| `box-and-birdhouse` | finger-jointed trays, lids and birdhouses, laser-ready | Pillow (engraving) |

**This repo is the source of truth.** There is no separate source tree and no
build output to keep in sync — edit a skill file, run `rebuild.sh`, commit,
push.

Every command students run goes through the **pinned Python sandbox** each
skill carries (`ensure-runtime.sh` / `ensure-runtime.ps1` for Windows): uv
downloads a pinned CPython into `~/.venvs/ent164-maker` with pinned Pillow and
PyYAML. Nothing ever uses or changes the student's own Python, even a matching
one.

## Editing a skill

```bash
# 1. change something
$EDITOR breadboard-wiring/circuits/led.yml

# 2. rebuild the index (rewrites index.json only)
./tools/skill-publish/rebuild.sh

# 3. publish
git add -A && git commit -m "..." && git push

# 4. verify what students will actually get
curl -s https://tuftsmaker.github.io/skills/index.json
```

Steps 2 and 3 are not optional together. **Editing without rebuilding means
students get nothing** — opencode only re-downloads when a skill's `version`
changes, and that version is a hash of the skill's contents. The pre-commit
hook does the rebuild for you; install it once per clone:

```bash
scripts/install-git-hooks.sh
```

## Why the version exists

`index.json` lists every file plus a content hash:

```json
{
  "skills": [
    { "name": "maker", "version": "bc63971a6e02", "files": ["SKILL.md", "..."] }
  ]
}
```

opencode fetches `index.json`, compares each `version` against what it cached,
and only re-downloads when it differs. The hash is derived from the files:

- edit a file → new version → students update on next start
- push with no changes → same version → nobody re-downloads anything

You never bump a version by hand. `build-index.py --version X` exists if you
ever need to force one.

## Rules that will bite you

**`files` must list everything.** opencode does not fetch directories
recursively. `rebuild.sh` derives the list from the directory, so this cannot
drift — but never hand-edit `index.json`.

**Jekyll must stay off.** `.nojekyll` at the repo root is load-bearing: without
it GitHub Pages runs Jekyll, which converts `SKILL.md` to HTML (so the `.md`
404s) and skips `bbd/__init__.py` because it starts with an underscore.
opencode needs both served verbatim. Do not delete it.

**Failures are silent.** If a file 404s, the skill simply does not appear, with
only a log line on the student's machine. Always curl after pushing, and check
that every file in the index actually returns 200:

```bash
python3 - <<'PY'
import json, urllib.request
base = "https://tuftsmaker.github.io/skills/"
idx = json.load(urllib.request.urlopen(base + "index.json"))
for s in idx["skills"]:
    for rel in s["files"]:
        code = urllib.request.urlopen(f"{base}{s['name']}/{rel}").getcode()
        print(code, rel)
PY
```

**The ensure-runtime copies must stay identical.** Each skill carries its own
`ensure-runtime.sh` / `ensure-runtime.ps1` because students download skills
independently; `rebuild.sh` refuses a tree whose copies have drifted, and CI
runs the bootstrap on both Linux and Windows.

## Student-facing docs

The class site documents the skills and the one-sentence install:

- setup guide: <https://tuftsmaker.github.io/ENT-164/opencode-deepseek-guide/guide.html>
- handout: `handouts/add-class-tools.html` in the site repo

A change that alters what those pages say (the URL, a package, how a skill is
installed) means updating them in the site repo — they own the guide's PDF and
the Canvas copy of the page.

## CI

`.github/workflows/check.yml` proves, on every push:

- `index.json` matches the skills (rebuild + `git diff --exit-code`),
- the sandbox bootstraps from nothing and all three skills run on Linux,
- the same bootstrap runs under Windows PowerShell and a diagram renders.
