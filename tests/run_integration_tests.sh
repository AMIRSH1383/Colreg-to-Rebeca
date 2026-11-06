#!/usr/bin/env bash
# Uses the active Python/virtual environment; no installer, downloads, or global writes.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python -m pytest -q -m requires_rmc "$@"
