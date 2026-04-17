"""
Run all tests in the current directory and subdirs.
PROMPT> python test.py

Behavior:
- If not already running with the worker_plan venv, re-executes itself with it so project deps are available.
- Keeps cwd at repo root and adds worker_plan to PYTHONPATH so worker_plan_internal/worker_plan_api imports resolve without extra setup.
- Ensures cross-service test dependencies from `mcp_cloud/requirements.txt` are installed in the active test venv.
- Then discovers and runs all test_*.py under the repo once.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
import logging
import unittest

# If we're not already using the worker_plan virtualenv, re-exec into it.
PROJECT_ROOT = Path(__file__).resolve().parent
_RERUN_ENV = "PLANEXE_TEST_RERUN"
if os.environ.get(_RERUN_ENV) != "1":
    worker_python = PROJECT_ROOT / "worker_plan" / ".venv" / "bin" / "python"
    current_python = Path(sys.executable).resolve()
    worker_resolved = worker_python.resolve() if worker_python.is_file() else None

    if worker_resolved is None:
        sys.stderr.write(
            "No project virtualenv found. Please create one:\n"
            "  cd worker_plan && python3.13 -m venv .venv && source .venv/bin/activate && pip install -e .\n"
        )
        sys.exit(1)

    if current_python != worker_resolved:
        env = os.environ.copy()
        env[_RERUN_ENV] = "1"
        extra_paths = [str(PROJECT_ROOT / "worker_plan")]
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join(extra_paths + ([existing] if existing else []))
        print(f"Re-running tests with venv interpreter: {worker_python}", file=sys.stderr)
        completed = subprocess.run([str(worker_python), __file__], env=env, cwd=str(PROJECT_ROOT), check=False)
        sys.exit(completed.returncode)

REQUIRED_TEST_MODULES = ("pydantic", "mcp", "flask_sqlalchemy")
MCP_REQUIREMENTS = PROJECT_ROOT / "mcp_cloud" / "requirements.txt"


def _missing_modules(modules: tuple[str, ...]) -> list[str]:
    return [name for name in modules if importlib.util.find_spec(name) is None]


def _ensure_cross_service_dependencies() -> None:
    missing = _missing_modules(REQUIRED_TEST_MODULES)
    if not missing:
        return

    if not MCP_REQUIREMENTS.is_file():
        sys.stderr.write(
            "Missing test dependencies and requirements file not found.\n"
            f"Missing modules: {', '.join(missing)}\n"
            f"Expected requirements file: {MCP_REQUIREMENTS}\n"
        )
        sys.exit(1)

    print(
        f"Installing missing cross-service test dependencies: {', '.join(missing)}",
        file=sys.stderr,
    )
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(MCP_REQUIREMENTS)],
            cwd=str(PROJECT_ROOT),
        )
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            "Failed to install cross-service test dependencies.\n"
            f"Missing modules: {', '.join(missing)}\n"
            "Install them manually in the test venv, then rerun:\n"
            f"  {sys.executable} -m pip install -r {MCP_REQUIREMENTS}\n"
        )
        sys.exit(exc.returncode or 1)

    still_missing = _missing_modules(REQUIRED_TEST_MODULES)
    if still_missing:
        sys.stderr.write(
            "Cross-service test dependencies are still missing after installation.\n"
            f"Missing modules: {', '.join(still_missing)}\n"
            "Install them manually in the test venv, then rerun:\n"
            f"  {sys.executable} -m pip install -r {MCP_REQUIREMENTS}\n"
        )
        sys.exit(1)


_ensure_cross_service_dependencies()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
loader = unittest.TestLoader()
tests = loader.discover(pattern="test_*.py", start_dir=".")
runner = unittest.TextTestRunner(buffer=False)
runner.run(tests)
