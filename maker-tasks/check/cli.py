#!/usr/bin/env python3
"""Check a submission against a task.

    python3 check/cli.py --task cad-01-first-sketch part.dxf
    python3 check/cli.py --task cad-03-cut-a-hole --submission ~/submission/
    python3 check/cli.py --task cad-01-first-sketch part.dxf --json
    python3 check/cli.py --task cad-01-first-sketch part.dxf --svg
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

import dxf_reader  # noqa: E402
import laser_svg  # noqa: E402
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
    parser.add_argument("--svg", nargs="?", const="", metavar="PATH",
                        help="also write the laser-ready SVG (default: "
                             "<name>-laser-ready.svg beside the DXF)")
    parser.add_argument("--svg-margin", type=float, default=0.0,
                        help="margin around the part in the SVG, in mm (with --svg)")
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

    if args.svg is not None:
        code = _write_svg(submission, report, args.svg, args.svg_margin)
        if code:
            return code

    if report.failures:
        return 1
    return 0


def _write_svg(submission, report, target, margin) -> int:
    """Write the laser-ready SVG for the submission's DXF. Returns an exit code
    only on failure (0 / None means carry on)."""
    dxf = submission.dxf()
    if dxf is None:
        print("error: no DXF in the submission to convert", file=sys.stderr)
        return 2

    try:
        out, rep, notes = laser_svg.convert(dxf, target or None, margin)
    except dxf_reader.DxfError as exc:
        print(f"error: {dxf.name}: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"\nLaser-ready SVG")
    print(f"  wrote : {out}")
    print(f"  size  : {rep['part_w']:.3f} x {rep['part_h']:.3f} mm on a "
          f"{rep['page_w']:.3f} x {rep['page_h']:.3f} mm page")
    print(f"  style : #ff0000, no fill, hairline — {rep['shapes']} cut path(s)")
    for n in notes:
        print(f"  note  : {n}")
    for c in rep.get("coincident", []):
        print(f"  CHECK : {c['count']} entities cut the same line ({c['where']})")
        print(f"          — the laser fires on each one, so remove the duplicate "
              f"in Onshape and re-export")
    if rep["off_layer"]:
        print(f"  CHECK : geometry on unexpected layers: {rep['off_layer']}")
    if report.failures:
        print("  NOTE  : this file still reflects the DXF above — fix the [FIX] "
              "items in Onshape, re-export, and run this again.")
    return 0


def _submission_from_args(args):
    if args.submission:
        return runner.load_submission(args.submission)

    if not args.paths:
        raise runner.TaskError("give me a file, or a folder with --submission")

    if len(args.paths) == 1:
        sub = runner.load_submission(args.paths[0])
        # A single file still has a sibling manifest.md worth reading: the
        # documented one-liner (`cli.py --task ... part.dxf`) must not silently
        # ignore the same folder's manifest, or the link/self-check criteria
        # always fail on a submission that is actually complete.
        if sub.manifest is None and sub.source is not None:
            root = sub.source if sub.source.is_dir() else sub.source.parent
            sub.manifest = runner._manifest_from(sub, root=root)
        return sub

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
