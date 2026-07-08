# HANDOFF — המשך פתרון ההורדה האוטומטית (להרצה ב-Claude Code מקומי על Windows)

מסמך זה מיועד ל-Claude Code שרץ **על המחשב של המשתמש (Windows)**, שם יש גישת
רשת מלאה ל-`decisions.court.gov.il` ואפשר לבדוק מול השרת האמיתי — בניגוד לסביבה
המרוחקת שבה נבנה הפרויקט (שם ה-proxy חוסם את האתר, ולכן כל ניסיון היה "עיוור").

## המטרה
הורדה יומית אוטומטית של פסקי הדין מ-30 הימים האחרונים מהמאגר, ועדכון מסד הנתונים.
הקוד הרלוונטי: `fetch_daily.py`. פרטי הגישה: קובץ `.env` (DECISIONS_USER / DECISIONS_PASSWORD).

## מה כבר עובד (אין צורך לגעת)
- אפליקציית החיפוש (`app.py`, חבילת `zot/`) — חיפוש רגיל + AI. תקין.
- צנרת הקליטה (`zot/ingest.py`): קוראת `documents/**` (כולל תת-תיקיות תאריך),
  מחלצת מטא-דאטה מגוף פסק הדין (בית משפט, מספר תיק, צדדים, שופט, סוג החלטה),
  תומכת ב-.docx/.pdf/.txt, מעדיפה docx על pdf. **נבדק ועובד.**
- כלומר: ברגע שהקבצים יורדים ל-`documents/<תאריך>/`, כל השאר אוטומטי.

## מבנה השרת (נבדק מול צילומי מסך)
- IIS Directory Listing: השורש `/` מכיל תיקיות בשם תאריך (`2026-7-7/` וכו').
- כל תיקיית תאריך מכילה זוגות `{hash}.docx` + `{hash}.pdf`.
- אימות: **NTLM/Negotiate** (Windows Auth). כותרת: `WWW-Authenticate: NTLM, Negotiate`.
- לפני ה-IIS יש **WAF** שמחזיר דף חסימה אדום ("זוהתה פעילות בלתי מורשת",
  ‏`/SecurityPage/…`) לכל לקוח שאינו דפדפן.

## מה נבדק וכשל (חשוב — אל תחזור על זה)
| שיטה | TLS | תוצאה |
|---|---|---|
| `requests` רגיל | OpenSSL | ניתוק (WAF, 10054) |
| `requests_ntlm` + כותרות דפדפן | OpenSSL | **דף חסימה** של ה-WAF (200, לא הרשימה) |
| `curl.exe --ntlm` (מובנה ב-Windows) | Schannel | נחסם ע"י ה-WAF (exit 56) |
| `curl_cffi` (impersonate=chrome) + Basic | BoringSSL | עובר WAF, מגיע ל-IIS → 401 (צריך NTLM) |
| `curl_cffi` + NTLM ידני (spnego), HTTP/1.1 כפוי | BoringSSL | עובר WAF → **401** גם אחרי Type3 |

מסקנות מוכחות:
- **רק טביעת האצבע של Chrome עוברת את ה-WAF** → חייבים `curl_cffi` (או דפדפן אמיתי).
- `curl_cffi` בנוי על **BoringSSL שלא תומך ב-NTLM מובנה**.
- NTLM ידני מעל `curl_cffi`: החיבור **כן** נשמר (נבדק מקומית), HTTP/1.1 נכפה,
  ה-tokens של spnego תקינים — ובכל זאת 401.

## החשד המרכזי להמשך
**Extended Protection / Channel Binding** ב-IIS: ה-NTLM Type3 חייב לכלול את
`tls-server-end-point` — hash של תעודת ה-TLS של השרת. בלי זה מתקבל 401 בדיוק כפי
שראינו. זה כנראה החלק החסר.

## מה לנסות מקומית (עכשיו אפשר לבדוק מול השרת!)
1. **Channel binding** (הכי סביר):
   - להשיג את תעודת ה-TLS של השרת. אפשר דרך `curl_cffi` (CurlInfo.CERTINFO,
     יש להפעיל CURLOPT_CERTINFO) — הטביעה של Chrome עוברת את ה-WAF ומקבלת את התעודה.
   - לחשב `tls-server-end-point` לפי RFC 5929 (hash לפי אלגוריתם החתימה של התעודה;
     ברירת מחדל SHA-256).
   - להעביר ל-`spnego.client(..., channel_bindings=GssChannelBindings(
     application_data=b"tls-server-end-point:"+cert_hash))`.
   - לבדוק אם ה-401 הופך ל-200. **עכשיו אפשר לבדוק את זה מולם ישירות.**
2. אם לא — **דפדפן אמיתי**: Playwright/Chromium (TLS אמיתי עובר WAF, ו-Chromium
   מטפל ב-NTLM+channel binding). האתגר: הזנת סיסמה מפורשת ל-NTLM (‎--auth-server-allowlist‎
   משתמש ב-Windows SSO; `http_credentials` של Playwright כנראה לא תומך ב-NTLM).
   כדאי לבדוק גישה עם פרופיל Chrome אמיתי ששומר את הסיסמה.

## פקודות שימושיות
```
pip install -r requirements.txt          # כולל curl_cffi, pyspnego, requests_ntlm, playwright
python fetch_daily.py                     # מדפיס לכל מנוע: סטטוס + תיקיות שזוהו
```
מנוע ה-NTLM הידני נמצא ב-`fetch_daily.py` בפונקציה `_curl_cffi_ntlm_engine`.
בחירת המנוע ב-`select_engine` (בוחר את זה שמחזיר רשימת תיקיות אמיתית, לא דף חסימה).

## הערה
המשתמש אינו טכני — יש להסביר צעדים בפשטות, ולבצע את החלק הטכני עצמאית ככל האפשר
(עכשיו אפשר, כי יש גישה לרשת ואפשר לבדוק).
