@echo off
REM Daily run (Windows Task Scheduler): downloads new decisions, uploads new
REM files + rebuilds the index (fetch_daily.py), then uploads the updated
REM index.db to R2 (too big for git's 100MB limit). Logs to daily_log.txt.
cd /d "%~dp0"
echo ==== %date% %time% ==== >> daily_log.txt
python fetch_daily.py >> daily_log.txt 2>&1
python -c "from zot.storage import upload_index; upload_index()" >> daily_log.txt 2>&1
