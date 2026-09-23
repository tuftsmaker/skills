"""The criterion report — what every check returns, and what a person reads.

One vocabulary only:

    pass      the criterion is met
    fail      the criterion is not met; the message says how to fix it
    review    cannot be decided by a program (a photo, a link, a demo)

`review` is not a soft pass. It exists so a task can state, in the file, that a
human has to look — and so the grader can never quietly sign off the parts of
a task that only a person can judge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PASS = "pass"
FAIL = "fail"
REVIEW = "review"

ICONS = {PASS: "PASS", FAIL: "FAIL", REVIEW: "REVIEW"}


@dataclass
class CheckResult:
    status: str
    detail: str = ""
    fix: str = ""
    evidence: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status != FAIL


def passed(detail="", **evidence):
    return CheckResult(PASS, detail, "", evidence or {})


def failed(detail, fix="", **evidence):
    return CheckResult(FAIL, detail, fix, evidence or {})


def needs_review(detail="", **evidence):
    return CheckResult(REVIEW, detail, "", evidence or {})


@dataclass
class CriterionResult:
    id: str
    title: str
    status: str
    detail: str = ""
    fix: str = ""
    evidence: dict = field(default_factory=dict)


@dataclass
class Report:
    task: str
    title: str
    student: str | None
    criterion_results: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    # -- roll-ups ---------------------------------------------------------

    @property
    def failures(self):
        return [c for c in self.criterion_results if c.status == FAIL]

    @property
    def reviews(self):
        return [c for c in self.criterion_results if c.status == REVIEW]

    @property
    def verdict(self) -> str:
        """`ready` when every program-checkable criterion passes; the human
        still signs off whatever is in `review`. Never "qualified"."""
        return "fix" if self.failures else "ready"

    def summary(self) -> str:
        passed_n = sum(1 for c in self.criterion_results if c.status == PASS)
        bits = [f"{passed_n} passed"]
        if self.failures:
            bits.append(f"{len(self.failures)} to fix")
        if self.reviews:
            bits.append(f"{len(self.reviews)} for human review")
        return ", ".join(bits)

    # -- rendering --------------------------------------------------------

    def to_text(self) -> str:
        lines = [f"{self.title}  ({self.task})"]
        if self.student:
            lines.append(f"Student: {self.student}")
        lines.append("")
        for c in self.criterion_results:
            mark = {"pass": "[ok]  ", "fail": "[FIX] ", "review": "[?]   "}[c.status]
            lines.append(f"{mark}{c.title}")
            if c.detail:
                lines.append(f"      {c.detail}")
            if c.fix:
                lines.append(f"      → {c.fix}")
        lines.append("")
        lines.append(f"{self.summary()}.")
        if self.failures:
            lines.append("Not ready yet — fix the flagged items and check again.")
        elif self.reviews:
            lines.append("Ready to submit. The items marked [?] are judged by a person.")
        else:
            lines.append("Ready to submit.")
        for n in self.notes:
            lines.append(f"note: {n}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "title": self.title,
            "student": self.student,
            "verdict": self.verdict,
            "summary": self.summary(),
            "criteria": [
                {
                    "id": c.id,
                    "title": c.title,
                    "status": c.status,
                    "detail": c.detail,
                    "fix": c.fix,
                    "evidence": c.evidence,
                }
                for c in self.criterion_results
            ],
            "notes": self.notes,
        }


@dataclass
class Submission:
    """Everything a student handed in for one task."""

    files: dict = field(default_factory=dict)  # name (lowercase) -> Path
    manifest: dict | None = None
    source: Path | None = None  # the folder or zip it was read from

    def find(self, *names) -> Path | None:
        for name in names:
            if name.lower() in self.files:
                return self.files[name.lower()]
        return None

    def dxf(self) -> Path | None:
        for name, path in self.files.items():
            if name.endswith(".dxf"):
                return path
        return None

    def has(self, name) -> bool:
        return name.lower() in self.files


def read_manifest(path: Path) -> dict:
    """A student-written `manifest.md`/`manifest.txt` of `key: value` lines."""
    out = {}
    if not path or not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("|"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip().lower().replace(" ", "_")] = value.strip()
    return out
