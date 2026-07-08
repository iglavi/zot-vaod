# העלאת האפליקציה המלאה (כולל חיפוש חכם) ל-Streamlit Community Cloud — בחינם

האתר הסטטי (`site/giluy-naot.html`) כולל רק את החיפוש הרגיל. כדי לקבל גם את
**החיפוש החכם (AI)**, מריצים את האפליקציה המלאה על Streamlit Community Cloud —
שירות אירוח חינמי שמתחבר ישירות ל-GitHub. ההעלאה לוקחת כ-3 דקות.

## מה שכבר מוכן בשבילכם

- הקוד נמצא ב-GitHub: **`iglavi/zot-vaod`**.
- `requirements.txt` ו-`app.py` בשורש הפרויקט — Streamlit יזהה אותם אוטומטית.
- **האינדקס נבנה אוטומטית** בעלייה הראשונה (אין צורך להריץ שום פקודה).
- המפתח שתגדירו כ-Secret מגושר אוטומטית ל-API של Anthropic.

לכן נשארו רק צעדים שדורשים את החשבון והמפתח האישיים שלכם:

## הצעדים

1. היכנסו ל-**[share.streamlit.io](https://share.streamlit.io)** והתחברו עם חשבון
   ה-GitHub שלכם (המשתמש `iglavi`). אשרו ל-Streamlit גישה ל-repositories.

2. לחצו על **"Create app"** → **"Deploy a public app from GitHub"**.

3. מלאו:
   - **Repository:** `iglavi/zot-vaod`
   - **Branch:** `main`
   - **Main file path:** `app.py`

4. לחצו על **"Advanced settings"** → בשדה **Secrets** הדביקו:

   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   # אופציונלי, להוזלת עלות:
   # ZOT_MODEL = "claude-sonnet-5"
   ```

   > את מפתח ה-API מקבלים בחשבון Anthropic שלכם:
   > [console.anthropic.com](https://console.anthropic.com) → API Keys.

5. לחצו **"Deploy"**. בפעם הראשונה זה לוקח כ-1–2 דקות (התקנת החבילות ובניית
   האינדקס). בסיום תקבלו כתובת ציבורית קבועה (למשל
   `https://giluy-naot.streamlit.app`) שאפשר לשתף.

## הערות

- **החיפוש הרגיל** יעבוד גם בלי מפתח API. **החיפוש החכם** ידרוש את המפתח שהגדרתם.
- מסד הנתונים המלא (`data/index.db`, כולל טקסט מלא של כל פסקי הדין) מתעדכן
  **אוטומטית כל בוקר** מהמחשב הביתי (ראו `SETUP_WINDOWS.md`) — אין צורך
  להעלות קבצים ל-repo באופן ידני.
- עלות: אירוח האפליקציה חינמי לחלוטין. התשלום היחיד הוא על שימוש ב-API של Anthropic
  בחיפוש החכם, לפי הצריכה בפועל (ניתן להוזיל עם `ZOT_MODEL = "claude-sonnet-5"`).

## אחסון קבצי המקור (PDF/Word) להורדה מהאתר — Cloudflare R2 (אופציונלי, חינמי)

בלי השלב הזה האתר עדיין מלא-פעיל (חיפוש רגיל וחכם, טקסט מלא). זה רק מוסיף
כפתור "הורדת הקובץ המקורי" לכל תיק.

1. פתחו חשבון חינמי ב-**[dash.cloudflare.com](https://dash.cloudflare.com)** (אם
   אין לכם עדיין).
2. בתפריט הצד: **R2 Object Storage** → **Create bucket**. תנו שם, למשל
   `giluy-naot-docs`. אזור: Automatic.
3. בעמוד ה-bucket → לשונית **Settings** → **Public access** → אפשרו
   **"Allow Access"** תחת **Public Development URL**. תקבלו כתובת בסגנון
   `https://pub-xxxxxxxxxxxx.r2.dev` — זו הכתובת הציבורית (`R2_PUBLIC_BASE_URL`).
4. חזרה לעמוד הראשי של R2 → **Manage R2 API Tokens** → **Create API Token** →
   הרשאה **Object Read & Write**, מוגבל ל-bucket שיצרתם. שמרו את שלושת הערכים
   שיוצגו **פעם אחת בלבד**: Access Key ID, Secret Access Key, ואת ה-Account ID
   (מופיע גם בסרגל הצד של R2).
5. הוסיפו ל-`.env` המקומי (במחשב הביתי, לא ב-repo):
   ```
   R2_ACCOUNT_ID=...
   R2_ACCESS_KEY_ID=...
   R2_SECRET_ACCESS_KEY=...
   R2_BUCKET=giluy-naot-docs
   R2_PUBLIC_BASE_URL=https://pub-xxxxxxxxxxxx.r2.dev
   ```
6. גם באתר הציבורי (Streamlit Cloud) צריך את הכתובת הציבורית כדי להציג את
   הכפתור: ב-**Secrets** של האפליקציה הוסיפו שורה `R2_PUBLIC_BASE_URL = "https://pub-...r2.dev"`
   (רק את הכתובת הציבורית — לא את מפתחות הגישה; אלה נשארים רק במחשב הביתי
   שמעלה את הקבצים).
7. מההרצה היומית הבאה, כל קובץ חדש שיורד יועלה אוטומטית ל-R2, ויופיע קישור
   הורדה לצדו באתר.

עלות: 10GB הראשונים חינם; מעבר לזה כ-$0.015 ל-GB בחודש **בלי עמלת הורדה** —
כלומר גם ארכיון של מיליון קבצים/טרה-בייט נשאר זול (כ-$15/חודש), ולא מתייקר
ככל שיותר אנשים מורידים מהאתר.
