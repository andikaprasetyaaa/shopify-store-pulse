#!/bin/bash
#
# Hourly Shopify Store Pulse sync entry point.
#
# Called by launchd (see scripts/com.storepulse.sync.plist).
# Safe to run manually too.
#
# Behaviour:
#   - incremental orders (only what changed since last run)
#   - full inventory snapshot, bucketed per day
#     (refreshed hourly, one snapshot retained/day)
#   - duplicates overwritten by primary key
#   - retries while another process holds the DuckDB file
#   - snapshots older than the retention window are pruned

set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/sync.log"

RETENTION_DAYS="${STORE_PULSE_RETENTION_DAYS:-30}"
SNAPSHOT_BUCKET="${STORE_PULSE_SNAPSHOT_BUCKET:-day}"
MAX_ATTEMPTS="${STORE_PULSE_MAX_ATTEMPTS:-3}"
RETRY_SLEEP="${STORE_PULSE_RETRY_SLEEP:-60}"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"
}

if [ ! -x "$PYTHON" ]; then
    log "FAIL virtualenv python not found at $PYTHON"
    exit 1
fi

# Keep the log from growing without bound (~5 MB).
if [ -f "$LOG_FILE" ] && [ "$(wc -c < "$LOG_FILE")" -gt 5242880 ]; then
    mv "$LOG_FILE" "$LOG_FILE.1"
fi

attempt=1
status=1

while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
    log "START attempt $attempt/$MAX_ATTEMPTS"

    # -u keeps progress streaming into the log
    # instead of appearing only when the run ends.
    "$PYTHON" -u -m scripts.sync_data \
        --incremental \
        --snapshot-bucket "$SNAPSHOT_BUCKET" \
        --retention-days "$RETENTION_DAYS" \
        >> "$LOG_FILE" 2>&1

    status=$?

    if [ "$status" -eq 0 ]; then
        log "DONE attempt $attempt succeeded"
        break
    fi

    log "WARN attempt $attempt failed with exit $status"

    if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
        sleep "$RETRY_SLEEP"
    fi

    attempt=$((attempt + 1))
done

if [ "$status" -ne 0 ]; then
    log "FAIL sync gave up after $MAX_ATTEMPTS attempts"
fi

exit "$status"
