#!/usr/bin/env python3
"""photofx — grid application launcher.

A .pyw entry point: on Windows it runs under pythonw with no console
window; on Linux it is a plain executable script. If the system Python
lacks Pillow but the project venv exists, the script re-executes itself
with the venv interpreter.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _venv_python():
    python = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    candidate = HERE / ".venv" / python
    return candidate if candidate.exists() else None


def _ensure_deps():
    try:
        import PIL  # noqa: F401
    except ImportError:
        venv = _venv_python()
        if venv is not None and os.environ.get("PHOTOFX_REEXEC") != "1":
            os.environ["PHOTOFX_REEXEC"] = "1"   # guard against re-exec loops
            os.execv(str(venv), [str(venv), str(__file__), *sys.argv[1:]])
        raise SystemExit("photofx needs Pillow — run: "
                         ".venv/bin/pip install -r requirements.txt")


_ensure_deps()
sys.path.insert(0, str(HERE))
from photofx.app.main import main  # noqa: E402

main()
