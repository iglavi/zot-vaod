@echo off
REM הרצה יומית של הורדת פסקי הדין ועדכון המאגר (עבור Windows Task Scheduler).
REM הסקריפט עובר לתיקיית הפרויקט, מריץ את ההורדה (שכוללת בתוכה גם העלאת
REM מסמכים חדשים ל-R2 וגם בניית אינדקס מחדש), ורושם יומן ל-daily_log.txt.
REM לבסוף מעלה את מסד הנתונים המעודכן (data\index.db) ל-R2 — לא ל-git,
REM כי הקובץ חורג מ-100MB (מגבלת הגודל הקשיחה של GitHub לקובץ בודד).
cd /d "%~dp0"
echo ==== %date% %time% ==== >> daily_log.txt
python fetch_daily.py >> daily_log.txt 2>&1
python -c "from zot.storage import upload_index; upload_index()" >> daily_log.txt 2>&1
