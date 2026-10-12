#!/usr/bin/env bash
# start.sh — set up the virtualenv if needed and launch photofx.
#
# The venv is created and activated INSIDE this script only; the calling
# shell is never modified, so nothing needs to be deactivated afterwards.

set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
PYTHON="$VENV/bin/python"
REQUIREMENTS="requirements.txt"

# --- init: create the venv if it is missing -------------------------------
if [ ! -x "$PYTHON" ]; then
    echo "[photofx] creating virtualenv in $VENV ..."
    python3 -m venv "$VENV"
fi

# --- deps: install Pillow if not yet installed ----------------------------
if ! "$PYTHON" -c "import PIL" >/dev/null 2>&1; then
    echo "[photofx] installing requirements ..."
    "$VENV/bin/pip" install -q -r "$REQUIREMENTS"
fi

# --- activate (affects only this script's shell) --------------------------
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# --- run -------------------------------------------------------------------
echo "[photofx] starting ..."
python -m photofx

# --- deactivate (explicit, for the sourced-invocation case) ----------------
deactivate 2>/dev/null || true
