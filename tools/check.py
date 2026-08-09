"""Run the local repository quality checks."""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> int:
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def main() -> int:
    if sys.version_info[:2] != (3, 14):
        print("EA Research Lab requires Python >=3.14,<3.15.", file=sys.stderr)
        return 1

    if not callable(getattr(uuid, "uuid7", None)):
        print("The active Python runtime does not provide uuid.uuid7().", file=sys.stderr)
        return 1

    commands = (
        [sys.executable, "-m", "compileall", "-q", "src", "tests", "tools"],
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_*.py",
        ],
    )

    for command in commands:
        return_code = _run(command)
        if return_code:
            return return_code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
