# Development

## Toolchain

EA Research Lab requires Python `>=3.14,<3.15`. The M1 environment and dependency lock were verified with Python 3.14.7.

The only functional third-party dependency in Phase 01 is `jsonschema[format]`. `setuptools` is used only as the package build backend. The Python standard library provides the test runner and local quality-check orchestration.

## Environment setup

Create and activate a project-local virtual environment:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On Command Prompt, activate it with:

```bat
.venv\Scripts\activate.bat
```

Install the exact locked environment, then install the project in editable mode without resolving dependencies again:

```text
python -m pip install -r requirements.lock
python -m pip install --no-build-isolation --no-deps --editable .
```

If PowerShell script execution prevents activation, invoke `.venv\Scripts\python.exe` explicitly for each command instead of changing the machine execution policy.

## Local quality gate

Run the complete local check with the project virtual environment active:

```text
python tools/check.py
```

The command verifies the Python 3.14 baseline and `uuid.uuid7()` availability, compiles the Python sources, and runs `unittest` discovery. A failing check returns a non-zero exit status.

Installing the `jsonschema[format]` extra does not activate format validation by itself. Schema validators must pass an explicit `FormatChecker`; the M1 negative test verifies this behavior.

M1 intentionally contains no provider, storage, API, analysis, UI, or MCP runtime implementation or scaffolding.
