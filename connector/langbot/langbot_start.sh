#!/bin/bash
# Startup script for LangBot connector

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

LOG_FILE="$SCRIPT_DIR/langbot.log"

echo "Starting LangBot connector..."
echo "Log file: $LOG_FILE"

# Start input handler (Flask webhook server)
python -u connector/langbot/langbot_input.py >> "$LOG_FILE" 2>&1 &
INPUT_PID=$!
echo "Started langbot_input.py with PID $INPUT_PID"

# Start output handler (async polling)
python -u connector/langbot/langbot_output.py >> "$LOG_FILE" 2>&1 &
OUTPUT_PID=$!
echo "Started langbot_output.py with PID $OUTPUT_PID"

echo "LangBot connector started"
echo "Input PID: $INPUT_PID, Output PID: $OUTPUT_PID"

wait

