@echo off
REM הרצה יומית של הורדת פסקי הדין ועדכון המאגר (עבור Windows Task Scheduler).
REM הסקריפט עובר לתיקיית הפרויקט, מריץ את ההורדה, ורושם יומן ל-daily_log.txt.
cd /d "%~dp0"
echo ==== %date% %time% ==== >> daily_log.txt
python fetch_daily.py >> daily_log.txt 2>&1
