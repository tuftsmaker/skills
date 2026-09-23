#!/usr/bin/env python3
"""Check a submission against a task.

    python3 check/cli.py --task cad-01-first-sketch part.dxf
    python3 check/cli.py --task cad-03-cut-a-hole --submission ~/submission/
    python3 check/cli.py --task cad-01-first-sketch part.dxf --json
    python3 check/cli.py --list

Exit codes: 0 every checkable criterion passes, 1 something must be fixed,
2 the submission could not be read at all.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import runner  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check",
        description="Check a task submission against its written criteria.",
    )
    parser.add_argument("--task", "-t", help="task id, e.g. cad-01-first-sketch")
    parser.add_argument("--submission", "-s", help="folder or zip containing the submission")
    parser.add_argument("paths", nargs="*", help="files to check (part.dxf, manifest.md, ...)")
    parser.add_argument("--json", action="store_true", help="print a JSON report")
    parser.add_argument("--list", action="store_true", help="list the tasks and exit")
    parser.add_argument("--student", help="name to record on the report")
    args = parser.parse_args(argv)

    if args.list or not args.task:
        for task in runner.list_tasks():
            kind = "unit " if task.get("kind") == "unit" else "task "
            print(f"{kind}{task['id']:<26} {task.get('title','')}")
        return 0

    try:
        task = runner.load_task(args.task)
    except runner.TaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        submission = _submission_from_args(args)
    except runner.TaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.student:
        submission.manifest = dict(submission.manifest or {})
        submission.manifest["student"] = args.student

    report = runner.run(task, submission)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.to_text())

    if report.failures:
        return 1
    return 0


def _submission_from_args(args):
    if args.submission:
        return runner.load_submission(args.submission)

    if not args.paths:
        raise runner.TaskError("give me a file, or a folder with --submission")

    if len(args.paths) == 1:
        return runner.load_submission(args.paths[0])

    # Several loose files: treat their common folder as the submission.
    paths = [Path(p).expanduser().resolve() for p in args.paths]
    parents = {p.parent for p in paths}
    if len(parents) == 1:
        folder = parents.pop()
        sub = runner.Submission(source=folder)
        for p in paths:
            sub.files[p.name.lower()] = p
        sub.manifest = runner._manifest_from(sub, root=folder)
        return sub

    sub = runner.Submission(source=None)
    for p in paths:
        sub.files[p.name.lower()] = p
    sub.manifest = runner._manifest_from(sub)
    return sub


if __name__ == "__main__":
    raise SystemExit(main())
