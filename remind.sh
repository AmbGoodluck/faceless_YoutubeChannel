#!/bin/bash
# Runs the posting reminder. Called by cron at 7am / 12pm / 4pm.
cd "$HOME/faceless_YoutubeChannel" || exit 1
source .venv/bin/activate
export $(grep -v '^#' .env | xargs) 2>/dev/null
python src/serve_next_clip.py >> to_post/reminder.log 2>&1
