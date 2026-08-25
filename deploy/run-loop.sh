#!/usr/bin/env bash
# Persistent launcher for the AI-Trader autonomous paper loop.
# Used by systemd / launchd / Docker / cron. Logs to trader/state/logs/.
set -euo pipefail

# repo root = parent of this script's dir
cd "$(dirname "$0")/.."

export PYTHONUNBUFFERED=1

# Tunables (override via environment or the service unit)
INTERVAL="${INTERVAL:-900}"      # seconds between cycles
DAILY_CAP="${DAILY_CAP:-5}"      # max new paper buys per UTC day
MODE="${MODE:---execute}"        # set MODE="" for dry-run

LOG_DIR="${LOG_DIR:-trader/state/logs}"
mkdir -p "$LOG_DIR"

echo "$(date -u +%FT%TZ) starting loop: interval=${INTERVAL}s cap=${DAILY_CAP} mode=${MODE:-dry-run}" \
  | tee -a "$LOG_DIR/loop.log"

exec python3 -m trader.cli loop ${MODE} --interval "$INTERVAL" --daily-cap "$DAILY_CAP" \
  >> "$LOG_DIR/loop.log" 2>&1
