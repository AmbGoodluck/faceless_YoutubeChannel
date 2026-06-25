#!/bin/bash
# Amadu Studios — one-command launcher
# Usage:
#   ./run.sh --new              generate a new episode (AI video)
#   ./run.sh --new --stills     generate with Ken-Burns only (free, no Replicate)
#   ./run.sh --part 2           generate Part 2
#   ./run.sh --preview 1        open Part 1 in media player
#   ./run.sh --publish 1        upload Part 1 to YouTube

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv/bin/activate"

# Activate venv
if [ -f "$VENV" ]; then
    source "$VENV"
else
    echo "ERROR: venv not found at $VENV"
    echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install requests anthropic edge-tts pillow"
    exit 1
fi

# Load .env
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

# Default to lipsync (AI video). Pass --stills to use Ken-Burns instead.
MODE="lipsync"
ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--stills" ]; then
        MODE="stills"
    else
        ARGS+=("$arg")
    fi
done

echo "Starting Amadu Studios (renderer: $MODE)..."
VIDEO_PROVIDER=$MODE python3 "$SCRIPT_DIR/amadu_studios/run.py" "${ARGS[@]}"
