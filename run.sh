#!/usr/bin/env bash
# ============================================================
#  Mihon Extension Builder - one-click launcher (macOS / Linux)
#  Run:  ./run.sh        (chmod +x run.sh the first time)
#  Sets up everything on first run, then opens the wizard.
# ============================================================
set -e
cd "$(dirname "$0")"

# 1. Find Python
PY=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
    echo "[ERROR] Python is not installed."
    echo "        Install Python 3.11+ from https://www.python.org/downloads/"
    exit 1
fi

# 2. Create the virtual environment on first run
if [ ! -x ".venv/bin/python" ]; then
    echo "First-time setup: creating an isolated environment..."
    "$PY" -m venv .venv
    echo "Installing dependencies (this happens only once)..."
    .venv/bin/python -m pip install --upgrade pip >/dev/null
    .venv/bin/python -m pip install -r requirements.txt
fi

# 3. Launch the wizard (or pass through any CLI args)
.venv/bin/python main.py "$@"
