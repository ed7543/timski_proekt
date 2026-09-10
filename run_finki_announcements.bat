@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo ============ %date% %time% ============ >> finki_announcements_log.txt
python -m backend.scripts.fetch_finki_announcements >> finki_announcements_log.txt 2>&1
