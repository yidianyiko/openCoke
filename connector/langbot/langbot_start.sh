#!/bin/bash
# Startup script for LangBot connector

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

LOG_FILE="$SCRIPT_DIR/langbot.log"

echo "Starting LangBot connector..."
echo "Log file: $LOG_FILE"

# Stop existing processes to avoid port conflicts / duplicate pollers
pkill -f "gunicorn.*langbot_input|python.*-m gunicorn.*langbot_input" 2>/dev/null || true
pkill -f "python.*connector/langbot/langbot_input.py" 2>/dev/null || true
pkill -f "python.*connector/langbot/langbot_output.py" 2>/dev/null || true
sleep 1

# Start input handler (Flask webhook server)
python -m gunicorn -w 2 -b 0.0.0.0:8081 --log-level info \
    connector.langbot.langbot_input:app >> "$LOG_FILE" 2>&1 &
INPUT_PID=$!
echo "Started langbot_input.py with Gunicorn (PID $INPUT_PID)"

# Start output handler (async polling)
python -u connector/langbot/langbot_output.py >> "$LOG_FILE" 2>&1 &
OUTPUT_PID=$!
echo "Started langbot_output.py with PID $OUTPUT_PID"

echo "LangBot connector started"
echo "Input PID: $INPUT_PID, Output PID: $OUTPUT_PID"

wait
