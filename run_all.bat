@echo off
chcp 65001 >nul
echo.
echo ====================================================
echo  מתקין חבילות...
echo ====================================================
pip install -r requirements.txt -q
playwright install chromium

echo.
echo ====================================================
echo  פותח 10 חלונות במקביל (2001-2010)...
echo ====================================================

start "scraper 2001" cmd /k python scraper.py config_2001.json
timeout /t 3 /nobreak >nul
start "scraper 2002" cmd /k python scraper.py config_2002.json
timeout /t 3 /nobreak >nul
start "scraper 2003" cmd /k python scraper.py config_2003.json
timeout /t 3 /nobreak >nul
start "scraper 2004" cmd /k python scraper.py config_2004.json
timeout /t 3 /nobreak >nul
start "scraper 2005" cmd /k python scraper.py config_2005.json
timeout /t 3 /nobreak >nul
start "scraper 2006" cmd /k python scraper.py config_2006.json
timeout /t 3 /nobreak >nul
start "scraper 2007" cmd /k python scraper.py config_2007.json
timeout /t 3 /nobreak >nul
start "scraper 2008" cmd /k python scraper.py config_2008.json
timeout /t 3 /nobreak >nul
start "scraper 2009" cmd /k python scraper.py config_2009.json
timeout /t 3 /nobreak >nul
start "scraper 2010" cmd /k python scraper.py config_2010.json

echo.
echo כל ה-10 scrapers הופעלו.
echo סגור חלון זה.
