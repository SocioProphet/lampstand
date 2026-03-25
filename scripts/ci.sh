#!/usr/bin/env bash
set -euo pipefail

# Keep the working tree clean when running locally.
export PYTHONDONTWRITEBYTECODE=1

python -m compileall -q lampstand
python -m unittest discover -s tests
