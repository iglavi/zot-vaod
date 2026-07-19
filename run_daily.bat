@echo off
REM Daily run (Windows Task Scheduler): downloads new decisions, uploads new
REM files + rebuilds the index + syncs new rows to Turso (all inside
REM fetch_daily.py - see zot/turso_sync.py), then also uploads index.db to
REM R2 as an off-site backup snapshot (no longer downloaded by the live
REM site once TURSO_DATABASE_URL is set - see README.md). Logs to daily_log.txt.
cd /d "%~dp0"
echo ==== %date% %time% ==== >> daily_log.txt
python fetch_daily.py >> daily_log.txt 2>&1
python -c "from zot.storage import upload_index; upload_index()" >> daily_log.txt 2>&1
