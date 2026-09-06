#!/bin/bash
# Linux equivalent of run_finki_announcements.bat - for use on a deployment
# server via crontab (see README.md, "Sync FINKI announcements into the Blog
# feed"). Local Windows dev machines should keep using the .bat file instead.
cd "$(dirname "$0")"
source .venv/bin/activate
echo "============ $(date) ============" >> finki_announcements_log.txt
python -m backend.scripts.fetch_finki_announcements >> finki_announcements_log.txt 2>&1
