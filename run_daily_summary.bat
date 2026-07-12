@echo off
REM Daily (18:30) run of the summary email script, for Windows Task Scheduler.
cd /d "%~dp0"
python daily_summary_email.py >> daily_summary_run.txt 2>&1
