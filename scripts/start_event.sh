#!/bin/sh
set -eu
project_root=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
event_python=${PHOTOBOOTH_PYTHON:-"$project_root/backend/.venv/bin/python"}
exec "$event_python" "$project_root/scripts/run_host.py" "$@"
