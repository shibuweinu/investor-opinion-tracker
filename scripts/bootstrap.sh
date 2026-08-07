#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python_bin=${PYTHON_BIN:-python3.11}

if ! command -v "$python_bin" >/dev/null 2>&1; then
  python_bin=python3
fi

"$python_bin" -c 'import sys; assert sys.version_info >= (3, 11), "需要 Python 3.11 或更高版本"'
"$python_bin" -m venv "$project_dir/.venv"
"$project_dir/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$project_dir/.venv/bin/python" -m pip install -e "$project_dir[mcp]"
"$project_dir/.venv/bin/opinion-tracker" doctor
