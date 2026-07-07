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
   - **Branch:** `claude/israeli-court-search-app-gtaie0`
     (או `main`, אם תמזגו קודם את השינויים ל-main)
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
- כדי לחפש בכל אלפי פסקי הדין (ולא רק בדוגמאות שב-`documents/`), העלו את קבצי
  ה-`.docx` ל-repo, או הצביעו על תיקייה אחרת עם משתנה הסביבה `ZOT_DOCS`, והריצו
  שוב את הבנייה (כפתור "בנייה מחדש של האינדקס" בסרגל הצד).
- עלות: אירוח האפליקציה חינמי לחלוטין. התשלום היחיד הוא על שימוש ב-API של Anthropic
  בחיפוש החכם, לפי הצריכה בפועל (ניתן להוזיל עם `ZOT_MODEL = "claude-sonnet-5"`).
