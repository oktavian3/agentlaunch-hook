#!/bin/bash
# SoulAgent Keeper Bot — Shell wrapper for cron job
# Runs the keeper-bot.py and logs output
# Designed for: cronjob(action='create', no_agent=True, script='scripts/keeper-bot.sh', schedule='0 */6 * * *')

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/../keeper-bot.log"

echo "==========================================" >> "$LOG_FILE"
echo "SoulAgent Keeper — $(date -u '+%Y-%m-%d %H:%M:%S UTC')" >> "$LOG_FILE"
echo "==========================================" >> "$LOG_FILE"

cd "$SCRIPT_DIR"

# Try python3, fallback to python
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "ERROR: No Python found" | tee -a "$LOG_FILE"
    exit 1
fi

# Check for web3
if ! $PYTHON -c "import web3" 2>/dev/null; then
    echo "Installing web3.py..." | tee -a "$LOG_FILE"
    pip install web3 -q 2>&1 | tee -a "$LOG_FILE"
fi

$PYTHON "$SCRIPT_DIR/keeper-bot.py" 2>&1 | tee -a "$LOG_FILE"

echo "" >> "$LOG_FILE"
echo "Done." >> "$LOG_FILE"
