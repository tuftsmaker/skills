#!/usr/bin/env python3
"""Build a publishable skills tree + index.json for opencode's `skills.urls`.

opencode fetches  <base>/index.json  and then every file listed there from
<base>/<skill>/<file>. This script copies the skills out of the repo, derives a
content-based version for each, writes the index, and can verify the result
against the same rules opencode applies.

Usage:
    build-index.py                  # build into ./dist
    build-index.py --verify         # check the built tree the way opencode does
    build-index.py --version 1.2.3  # force a version (otherwise content hash)
    build-index.py --serve 8000     # build, then serve ./dist for testing
"""

import argparse
import hashlib
import http.server
import json
import os
import re
import shutil
import socketserver
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_SRC = REPO  # the registry is the repo root; skills are its directories
DEFAULT_DIST = os.path.join(HERE, "dist")

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
WINDOWS_ABS = re.compile(r"^[A-Za-z]:")
URLISH = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")

# Directories at the repo root that are not skills: the publisher itself, the
# hook installer, and GitHub's workflow folder.
EXCLUDE_DIRS = {"__pycache__", ".git", ".github", "node_modules", ".venv",
                ".idea", "dist", "tools", "scripts"}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db", ".gitignore"}
# Editor droppings and backups. Anything left here would not just ship to
# students, it would change the version and force a re-download for everyone.
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".bak", ".swp", ".swo", ".tmp", ".orig", ".rej", "~")


# --- mirrors of the checks in opencode's SkillDiscovery -------------------

def safe_segment(value):
    """opencode isSafeSegment: one path component, no separators or dot-dots."""
    return (
        len(value) > 0
        and value not in (".", "..")
        and "/" not in value
        and "\\" not in value
        and "\0" not in value
    )


def safe_relpath(value):
    """opencode isSafeRelativePath: a plain relative path, not a URL."""
    if not value or "\\" in value or "\0" in value or "?" in value or "#" in value:
        return False
    if value.startswith("/") or WINDOWS_ABS.match(value) or URLISH.match(value):
        return False
    for segment in value.split("/"):
        if segment in ("", ".", ".."):
            return False
    return True


# --- building -------------------------------------------------------------

def collect_files(root):
    """All publishable files under root, as forward-slash relative paths."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for name in sorted(filenames):
            if name in EXCLUDE_FILES or name.endswith(EXCLUDE_SUFFIXES):
                continue
            full = os.path.join(dirpath, name)
            found.append(os.path.relpath(full, root).replace(os.sep, "/"))
    # SKILL.md first so the index reads naturally
    found.sort(key=lambda p: (p != "SKILL.md", p))
    return found


def content_version(root, files):
    """Deterministic version: same content => same version => no re-download.

    Text is hashed with LF endings, so the same commit produces the same
    version whether it was checked out on Windows (CRLF) or macOS (LF).
    """
    digest = hashlib.sha256()
    for rel in files:
        digest.update(rel.encode("utf-8"))
        with open(os.path.join(root, rel), "rb") as fh:
            digest.update(fh.read().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:12]


def skill_dirs(root):
    """Yield (name, path) for each skill folder directly under root."""
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(path) and name not in EXCLUDE_DIRS:
            yield name, path


def scan_skill(skill_dir, name, forced_version=None):
    """Validate one skill folder and return its index entry."""
    if not NAME_RE.match(name) or not safe_segment(name):
        raise SystemExit(
            f"skill folder {name!r} is not a valid name "
            f"(must match {NAME_RE.pattern})"
        )

    files = collect_files(skill_dir)
    if "SKILL.md" not in files:
        raise SystemExit(f"skill {name!r} has no SKILL.md")

    bad = [f for f in files if not safe_relpath(f)]
    if bad:
        raise SystemExit(f"skill {name!r} has unpublishable paths: {bad}")

    return {
        "name": name,
        "version": forced_version or content_version(skill_dir, files),
        "files": files,
    }


def write_index(root, skills):
    index = {"skills": skills}
    with open(os.path.join(root, "index.json"), "w") as fh:
        json.dump(index, fh, indent=2)
        fh.write("\n")
    return index


def build_in_place(root, forced_version=None, quiet=False):
    """Rebuild root/index.json from the skill folders already sitting in root.

    Use this when the published tree IS the source of truth — editing a skill
    file and re-running this is all it takes to publish a change. Nothing is
    copied and nothing is deleted; only index.json is rewritten.
    """
    if not os.path.isdir(root):
        raise SystemExit(f"no skills directory at {root}")

    skills = []
    for name, path in skill_dirs(root):
        entry = scan_skill(path, name, forced_version)
        skills.append(entry)
        if not quiet:
            print(f"  {name:20} {entry['version']}  ({len(entry['files'])} files)")

    return write_index(root, skills)


def build(src, dist, forced_version=None, quiet=False):
    if not os.path.isdir(src):
        raise SystemExit(f"no skills directory at {src}")

    if os.path.isdir(dist):
        shutil.rmtree(dist)
    os.makedirs(dist)

    skills = []
    for name, path in skill_dirs(src):
        entry = scan_skill(path, name, forced_version)
        skills.append(entry)
        if not quiet:
            print(f"  {name:20} {entry['version']}  ({len(entry['files'])} files)")

        dest = os.path.join(dist, name)
        for rel in entry["files"]:
            target = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(path, rel), target)

    return write_index(dist, skills)


# --- verifying ------------------------------------------------------------

def verify(dist):
    """Re-check the built tree exactly the way opencode will read it."""
    index_path = os.path.join(dist, "index.json")
    if not os.path.isfile(index_path):
        raise SystemExit(f"missing {index_path} — run without --verify first")

    with open(index_path) as fh:
        index = json.load(fh)

    problems = []
    if not isinstance(index.get("skills"), list):
        raise SystemExit("index.json has no 'skills' array")

    for skill in index["skills"]:
        name = skill.get("name", "")
        files = skill.get("files", [])
        tag = name or "<unnamed>"

        if not safe_segment(name):
            problems.append(f"{tag}: unsafe skill name")
            continue
        if not NAME_RE.match(name):
            problems.append(f"{tag}: name does not match {NAME_RE.pattern}")
        if not files:
            problems.append(f"{tag}: empty files list")
        if "SKILL.md" not in files and f"{name}.md" not in files:
            problems.append(f"{tag}: files must include SKILL.md")

        root = os.path.join(dist, name)
        if not os.path.isdir(root):
            problems.append(f"{tag}: folder missing from dist")
            continue

        for rel in files:
            if not safe_relpath(rel):
                problems.append(f"{tag}: unsafe path {rel!r}")
                continue
            if not os.path.isfile(os.path.join(root, rel)):
                problems.append(f"{tag}: listed but missing on disk: {rel}")

        # files present on disk but absent from the index would never ship
        on_disk = set(collect_files(root))
        missing_from_index = sorted(on_disk - set(files))
        if missing_from_index:
            problems.append(f"{tag}: on disk but not listed: {missing_from_index}")

    if problems:
        print("index.json FAILED verification:")
        for p in problems:
            print("  - " + p)
        return False

    total = sum(len(s.get("files", [])) for s in index["skills"])
    print(f"index.json OK — {len(index['skills'])} skill(s), {total} files")
    return True


def serve(dist, port):
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=dist, **kw)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        print(f"\nserving {dist}")
        print(f"  index:  http://127.0.0.1:{port}/index.json")
        for name in sorted(os.listdir(dist)):
            if os.path.isdir(os.path.join(dist, name)):
                print(f"  skill:  http://127.0.0.1:{port}/{name}/SKILL.md")
        print("\npoint opencode at:  \"skills\": { \"urls\": [\"http://127.0.0.1:%d/\"] }" % port)
        print("Ctrl-C to stop\n")
        httpd.serve_forever()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=DEFAULT_SRC, help="skills source directory")
    ap.add_argument("--dist", default=DEFAULT_DIST, help="output directory")
    ap.add_argument("--in-place", action="store_true",
                    help="treat --src as both source and output; only rewrite index.json")
    ap.add_argument("--version", help="force this version instead of the content hash")
    ap.add_argument("--verify", action="store_true", help="verify an existing build")
    ap.add_argument("--serve", type=int, metavar="PORT", help="serve the build for testing")
    args = ap.parse_args()

    if args.verify:
        sys.exit(0 if verify(args.dist if not args.in_place else args.src) else 1)

    if args.in_place:
        root = args.src
        print(f"rebuilding index in place at {root}")
        build_in_place(root, args.version)
        print(f"\nwrote {os.path.join(root, 'index.json')}")
        if not verify(root):
            sys.exit(1)
        if args.serve:
            serve(root, args.serve)
        return

    print(f"building from {args.src}")
    build(args.src, args.dist, args.version)
    print(f"\nwrote {os.path.join(args.dist, 'index.json')}")

    if not verify(args.dist):
        sys.exit(1)

    if args.serve:
        serve(args.dist, args.serve)


if __name__ == "__main__":
    main()
