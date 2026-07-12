"""CLI import contracts for tools invoked by file path in CI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("script", "interpreter_args"),
    [
        ("tools/build_web.py", ("-I",)),
        ("tools/evaluate_web_feasibility.py", ()),
    ],
)
def test_tool_supports_direct_script_execution(
    script: str,
    interpreter_args: tuple[str, ...],
) -> None:
    completed = subprocess.run(
        [sys.executable, *interpreter_args, script, "--help"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
