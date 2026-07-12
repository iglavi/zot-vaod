@echo off
REM Periodic run of the confidentiality bot, for Windows Task Scheduler.
REM The bot itself writes a detailed log to confidentiality_bot_log.txt.
cd /d "%~dp0"
python confidentiality_bot.py >> confidentiality_bot_run.txt 2>&1
