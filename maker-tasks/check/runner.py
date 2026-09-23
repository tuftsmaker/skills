"""Read a task definition, apply its criteria to a submission, produce a Report.

This is the single entry point used by the student skill, the CLI and the
grader. It performs no network access and writes nothing outside the report
text it returns.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

import checks
import dxf_reader
from report import (
    CriterionResult,
    Report,
    Submission,
    read_manifest,
)

TASKS_DIR = Path(__file__).resolve().parent.parent / "tasks"  # shipped with the skill


class TaskError(Exception):
    """A task or submission could not be read or checked."""


class MissingDependency(TaskError):
    """A required third-party module is not installed.

    A `TaskError` so the CLI and the grader already report it in their own
    words, but `list_tasks` deliberately re-raises it instead of skipping: it
    is the difference between "PyYAML is missing" and "there are no tasks", and
    the second one silently builds an empty catalog from nothing.
    """


YAML_HINT = (
    "this checker needs pyyaml: python3 -m pip install -r requirements.txt "
    "(or: python3 -m pip install --user pyyaml)"
)


def load_task(task_id) -> dict:
    import json
    import re

    task_id = str(task_id)
    path = TASKS_DIR / f"{task_id}.yml"
    if not path.exists():
        matches = sorted(TASKS_DIR.glob("*.yml"))
        near = [p.stem for p in matches if task_id.lower() in p.stem.lower()]
        extra = f" Did you mean: {', '.join(near)}?" if near else ""
        raise TaskError(f"no task '{task_id}'.{extra}")
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        task = yaml.safe_load(text)
    except ImportError:
        # Not a TaskError's usual meaning: the task exists and is fine, the
        # environment is not. Say so where it cannot be mistaken for one.
        raise MissingDependency(YAML_HINT) from None
    task.setdefault("id", path.stem)
    return task


def list_tasks() -> list:
    out = []
    for p in sorted(TASKS_DIR.glob("*.yml")):
        try:
            out.append(load_task(p.stem))
        except MissingDependency:
            # Re-raise: without this, a missing dependency reduces the catalog
            # to zero tasks, and every caller then reports success over an
            # empty set.
            raise
        except TaskError:
            continue
    return out


# ---------------------------------------------------------------- context


@dataclass
class Context:
    task: dict
    submission: Submission
    drawing: object = None
    dxf_path: Path | None = None
    manifest: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    other_results: list = field(default_factory=list)  # criteria already run


def build_context(task: dict, submission: Submission) -> Context:
    ctx = Context(task=task, submission=submission)
    ctx.manifest = submission.manifest or {}

    dxf_path = submission.dxf()
    if dxf_path is not None:
        ctx.dxf_path = dxf_path
        try:
            ctx.drawing = dxf_reader.read(dxf_path)
        except dxf_reader.DxfError as exc:
            ctx.warnings.append(f"{dxf_path.name}: {exc}")
            ctx.drawing = None
    return ctx


# ---------------------------------------------------------------- submission


def load_submission(path) -> Submission:
    """Accept a folder, a zip, or a single DXF file."""
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise TaskError(f"{path} does not exist")

    if path.is_file() and path.suffix.lower() == ".zip":
        import zipfile

        sub = Submission(source=path)
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                base = Path(name).name
                if base.startswith("."):
                    continue
                target = submission_dir(path) / base
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                sub.files[base.lower()] = target
        sub.manifest = _manifest_from(sub)
        return sub

    if path.is_file():
        sub = Submission(source=path)
        sub.files[path.name.lower()] = path
        return sub

    sub = Submission(source=path)
    for child in sorted(path.rglob("*")):
        if child.is_dir() or child.name.startswith("."):
            continue
        if child.suffix.lower() in (".md", ".txt", ".yml", ".yaml", ".json"):
            continue
        sub.files[child.name.lower()] = child
    sub.manifest = _manifest_from(sub, root=path)
    return sub


def _manifest_from(submission: Submission, root: Path | None = None):
    import tempfile

    for name in ("manifest.md", "manifest.txt"):
        if name in submission.files:
            return read_manifest(submission.files[name])
    if root is not None:
        for name in ("manifest.md", "manifest.txt"):
            p = root / name
            if p.exists():
                return read_manifest(p)
    return {}


def submission_dir(zip_path: Path) -> Path:
    """Where a zip's files are unpacked: a temp dir that survives the process."""
    import tempfile

    base = Path(tempfile.gettempdir()) / "skill-tasks" / zip_path.stem
    base.mkdir(parents=True, exist_ok=True)
    return base


# ---------------------------------------------------------------- run


def run(task, submission_path) -> Report:
    """`task` is a task dict or a task id."""
    if isinstance(task, str):
        task = load_task(task)
    if task.get("kind") == "unit":
        return run_unit(task, submission_path)

    submission = submission_path if isinstance(submission_path, Submission) else load_submission(submission_path)
    ctx = build_context(task, submission)

    results = []
    # The self-check criterion judges the rest of the run, so it goes last and
    # is handed what every other criterion found.
    ordered = sorted(task.get("criteria", []), key=lambda c: c.get("check", "").endswith("manifest_selfcheck"))
    for crit in ordered:
        ctx.other_results = results
        results.append(_run_criterion(crit, ctx))

    report = Report(
        task=task["id"],
        title=task.get("title", task["id"]),
        student=submission.manifest.get("student") if submission.manifest else None,
        criterion_results=results,
    )
    report.notes.extend(ctx.warnings)
    return report


def _run_criterion(crit: dict, ctx: Context) -> CriterionResult:
    cid = crit.get("id", "?")
    title = crit.get("title", cid)

    if crit.get("human"):
        detail = crit.get("review", "a person checks this")
        return CriterionResult(cid, title, "review", detail, "")

    check_name = crit.get("check")
    if not check_name:
        return CriterionResult(cid, title, "review", crit.get("review", ""), "")

    module_name, _, func_name = check_name.partition(".")
    if not func_name:
        return CriterionResult(cid, title, "review", f"unknown check '{check_name}'", "")

    try:
        module = importlib.import_module(module_name)
        fn = getattr(module, func_name)
    except (ImportError, AttributeError):
        return CriterionResult(cid, title, "review", f"unknown check '{check_name}'", "")

    args = dict(crit.get("args") or {})
    try:
        result = fn(ctx, **args)
    except checks.CheckError as exc:
        return CriterionResult(cid, title, "fail", str(exc), crit.get("fix", ""))
    except Exception as exc:  # a broken check must never look like a pass
        return CriterionResult(
            cid, title, "review", f"the check could not run ({type(exc).__name__}: {exc})", ""
        )

    if crit.get("fail") and result.status == "fail" and not result.fix:
        result.fix = crit["fail"]
    return CriterionResult(
        cid, title, result.status, result.detail or crit.get("detail", ""), result.fix, result.evidence
    )


# ---------------------------------------------------------------- units


def run_unit(task: dict, submissions) -> Report:
    """A qualification: every task in it must be signed off. `submissions` is a
    mapping of task id -> report (or None).

    A track with `status: planned` has no tasks yet by design, so running it is
    a mistake rather than a result: say so plainly.
    """
    if task.get("status") == "planned":
        report = Report(task=task["id"], title=task.get("title", task["id"]), student=None)
        report.notes.append(
            "this track is planned, not built: its tasks do not exist yet, so there "
            "is nothing to sign off."
        )
        return report

    results = []
    missing = []
    for task_id in task.get("tasks", []):
        child = submissions.get(task_id) if isinstance(submissions, dict) else None
        if child is None:
            missing.append(task_id)
            results.append(CriterionResult(task_id, task_id, "review", "not submitted yet"))
            continue
        if isinstance(child, str):
            child = {"verdict": child}
        verdict = child.get("verdict", "review")
        if verdict == "ready":
            results.append(CriterionResult(task_id, task_id, "pass", "files pass; signed by a person"))
        else:
            results.append(CriterionResult(task_id, task_id, "fail", "files need fixing"))

    report = Report(task=task["id"], title=task.get("title", task["id"]), student=None, criterion_results=results)
    if missing:
        report.notes.append(f"still to submit: {', '.join(missing)}")
    return report
