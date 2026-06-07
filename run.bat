@echo off
chcp 65001 >nul
echo.
echo ====================================================
echo  בדיקת התקנת Python...
echo ====================================================
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  שגיאה: Python לא מותקן או לא נמצא ב-PATH.
    echo  הורד מ: https://www.python.org/downloads
    echo  בהתקנה - סמן את: "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo.
echo ====================================================
echo  התקנת חבילות...
echo ====================================================
pip install -r requirements.txt
playwright install chromium

echo.
echo ====================================================
echo  מריץ את הסקראפר...
echo ====================================================
python scraper.py

echo.
pause
