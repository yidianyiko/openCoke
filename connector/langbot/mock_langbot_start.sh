#!/bin/bash
# Start local Mock LangBot server on port 8080

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

LOG_FILE="$SCRIPT_DIR/mock_langbot.log"

echo "Starting Mock LangBot on :8080"
python -u connector/langbot/mock_langbot_server.py >> "$LOG_FILE" 2>&1 &
echo "Mock LangBot PID: $!"
tail -n 50 -f "$LOG_FILE"

