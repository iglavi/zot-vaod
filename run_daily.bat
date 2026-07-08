@echo off
REM הרצה יומית של הורדת פסקי הדין ועדכון המאגר (עבור Windows Task Scheduler).
REM הסקריפט עובר לתיקיית הפרויקט, מריץ את ההורדה, ורושם יומן ל-daily_log.txt,
REM ולבסוף דוחף את מסד הנתונים (data\index.db בלבד — לא את קבצי ה-PDF/Word)
REM ל-GitHub, כדי שהאתר הציבורי (Streamlit Cloud) יתעדכן אוטומטית.
cd /d "%~dp0"
echo ==== %date% %time% ==== >> daily_log.txt
python fetch_daily.py >> daily_log.txt 2>&1
git fetch origin main >> daily_log.txt 2>&1
git merge --ff-only origin/main >> daily_log.txt 2>&1
git add -f data\index.db >> daily_log.txt 2>&1
git commit -m "Daily index update %date%" >> daily_log.txt 2>&1
git push origin main >> daily_log.txt 2>&1
