#!/usr/bin/env python3
"""Check a submission folder, write the report, and make the zip to upload.

This is the command the `maker-tasks` skill tells students to run, and the same
one a TA runs on a pulled submission. It never talks to the network.

    python3 check/check_submission.py --task cad-01-first-sketch ~/ent164/cad-01
    python3 check/check_submission.py --task cad-01-first-sketch ~/ent164/cad-01 --zip
    python3 check/check_submission.py --task cad-03-cut-a-hole submission.zip

Exit codes: 0 ready to submit, 1 fix something first, 2 could not read it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import runner  # noqa: E402


def manifest_fields(task: dict) -> list:
    """The manifest lines this task's checks read, in task order.

    Derived from the criteria so a task can never ask for a line nothing reads:
    the three manifest checks below are the only places the checker looks in the
    manifest, and this mirrors them.
    """
    fields = []
    for crit in task.get("criteria", []):
        check = (crit.get("check") or "").split(".")[-1]
        args = crit.get("args") or {}
        field = None
        if check == "manifest_source_link":
            field = args.get("field", "onshape_url")
        elif check == "manifest_material_thickness":
            field = "material_thickness"
        elif check == "manifest_field" and args.get("present", True):
            field = args.get("field")
        if field and field not in fields:
            fields.append(field)
    return fields


def build_folder(folder: Path, task: dict, student: str | None, onshape_url: str | None) -> None:
    """Write a starter manifest.md with just the lines this task checks."""
    manifest = folder / "manifest.md"
    if manifest.exists():
        return
    fields = manifest_fields(task)
    lines = [f"student: {student}"] if student else []
    for field in fields:
        value = onshape_url if field == "onshape_url" and onshape_url else ""
        lines.append(f"{field}: {value}")
    if not lines:
        return
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"wrote a starter manifest at {manifest} — opencode: fill in "
        f"{', '.join(fields) or 'the blank lines'}, then run this again."
    )


def make_zip(folder: Path, task: dict, student: str | None) -> Path:
    slug = student.replace(" ", "-").lower() if student else "submission"
    out = folder.parent / f"{task['id']}-{slug}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for child in sorted(folder.iterdir()):
            if child.is_dir() or child.name.startswith("."):
                continue
            if child.suffix.lower() in (".txt", ".json") and child.name != "manifest.txt":
                continue  # report files are not part of the submission
            zf.write(child, child.name)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="check-submission")
    parser.add_argument("--task", "-t", required=True)
    parser.add_argument("path", help="the submission folder, or a zip")
    parser.add_argument("--student", help="your name, for the report and the zip name")
    parser.add_argument("--onshape-url", help="your Onshape link, used to seed manifest.md")
    parser.add_argument("--zip", action="store_true", help="also build the zip to upload")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-report", action="store_true", help="do not write check-report.txt")
    args = parser.parse_args(argv)

    path = Path(args.path).expanduser().resolve()
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2

    try:
        task = runner.load_task(args.task)
    except runner.TaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if path.is_dir():
        build_folder(path, task, args.student, args.onshape_url)

    try:
        submission = runner.load_submission(path)
    except runner.TaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.student:
        submission.manifest = dict(submission.manifest or {})
        submission.manifest["student"] = args.student

    report = runner.run(task, submission)
    text = report.to_text()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(text)

    if path.is_dir() and not args.no_report:
        (path / "check-report.txt").write_text(text + "\n", encoding="utf-8")

    if args.zip and path.is_dir():
        out = make_zip(path, task, args.student or (submission.manifest or {}).get("student"))
        print()
        print(f"submission zip: {out}")
        print(f"upload it in Canvas under this task's assignment.")

    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
