#!/usr/bin/env bash
set -euo pipefail
python -m pip freeze > requirements.lock.txt
printf 'Saved the current environment; retain only after target-host checks pass.\n'
