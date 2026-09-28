#!/usr/bin/env python3
"""Where the class Python sandbox is, and how to get it.

Every class skill runs on one interpreter — a private, pinned Python kept in
``~/.venvs/ent164-maker`` — so nothing depends on the student's own Python.
The sandbox is created (and repaired) by the ``ensure-runtime.sh`` /
``ensure-runtime.ps1`` script beside this file, which every skill carries:

    sh ensure-runtime.sh

``python_with(["PIL"])`` is the path to use for work that needs a package. It
returns the sandbox interpreter when the sandbox exists and can import what is
needed, and otherwise raises an error naming the script to run. The interpreter
running this module is never a fallback: a matching student Python is exactly
what the sandbox exists to avoid.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

VENV = Path(os.environ.get("ENT164_VENV") or (Path.home() / ".venvs" / "ent164-maker"))
VENV_PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
DEFAULT_MODULES = ["PIL"]


def _import_ok(python: Path, modules) -> bool:
    """True when `python` can import every module in `modules`."""
    checks = ";".join(f"import {m}" for m in modules)
    try:
        return subprocess.run([str(python), "-c", checks],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def python_with(modules=DEFAULT_MODULES):
    """A path to the class sandbox interpreter, which can import `modules`.

    Raises RuntimeError naming the setup script when the sandbox is missing or
    incomplete. The running interpreter is not a fallback — see the module
    docstring.
    """
    modules = list(modules)
    if VENV_PYTHON.exists() and _import_ok(VENV_PYTHON, modules):
        return str(VENV_PYTHON)
    here = Path(__file__).resolve().parent
    raise RuntimeError(
        f"the class Python sandbox at {VENV} is not ready "
        f"(it must import {', '.join(modules)}).\n"
        f"    Run the skill's setup script once, then use the interpreter it "
        f"prints:\n"
        f"        sh {here / 'ensure-runtime.sh'}                 "
        f"# macOS / Linux\n"
        f"        powershell -ExecutionPolicy Bypass -File "
        f"{here / 'ensure-runtime.ps1'}   # Windows")


if __name__ == "__main__":
    try:
        print(python_with())
    except RuntimeError as exc:
        raise SystemExit(str(exc))
