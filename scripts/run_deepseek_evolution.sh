#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
printf '%s\n' \
  "NOTICE: run_deepseek_evolution.sh is now a compatibility forwarder." \
  "Use run_information_plan_evolution.sh as the stable entry." >&2
exec "$SCRIPT_DIR/run_information_plan_evolution.sh" "$@"
