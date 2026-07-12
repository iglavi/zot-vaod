# צ'אט עם סוכן Claude (Managed Agents)

אפליקציית צ'אט קטנה ב-Next.js שמתחברת ל-Claude Managed Agents API.
כל הקריאות ל-Anthropic נעשות **בצד השרת בלבד** — המפתח לעולם לא מגיע לדפדפן.
הגישה מוגנת בסיסמה אחת (`ACCESS_PASSWORD`) שנבדקת בשרת בכל בקשה.

## איך זה בנוי

```
agent-chat/
├── app/
│   ├── page.tsx              ← דף הצ'אט (עברית, RTL, מובייל)
│   ├── layout.tsx            ← עטיפת הדף (lang="he" dir="rtl")
│   ├── globals.css           ← עיצוב
│   └── api/
│       ├── login/route.ts    ← בדיקת סיסמה + הנפקת עוגיית גישה
│       └── chat/route.ts     ← יצירת session, שליחת הודעה, הזרמת תשובות (SSE)
└── lib/auth.ts               ← אימות העוגייה בכל בקשה
```

זרימת הודעה: הדפדפן שולח `POST /api/chat` → השרת פותח stream מול Anthropic,
שולח את ההודעה כ-event, ומזרים את האירועים חזרה לדפדפן בזמן אמת.
מזהה ה-session נשמר ב-localStorage בדפדפן כדי להמשיך שיחה קיימת;
כפתור "שיחה חדשה" מוחק אותו ומתחיל session חדש.

## משתני סביבה (4)

| שם | מה זה |
|---|---|
| `ANTHROPIC_API_KEY` | מפתח ה-API מ-[platform.claude.com](https://platform.claude.com) (מתחיל ב-`sk-ant-`) |
| `AGENT_ID` | מזהה הסוכן שיצרתם (מתחיל ב-`agent_`) |
| `ENVIRONMENT_ID` | מזהה סביבת הריצה של הסוכן (מתחיל ב-`env_`) |
| `ACCESS_PASSWORD` | סיסמת הגישה לאתר — בחרו סיסמה חזקה |

## הרצה מקומית

```bash
cd agent-chat
npm install
cp .env.local.example .env.local   # ומלאו את 4 הערכים
npm run dev                        # http://localhost:3000
```

## פריסה ל-Vercel

1. היכנסו ל-[vercel.com](https://vercel.com) והתחברו עם חשבון GitHub.
2. **Add New → Project** ובחרו את הריפו הזה.
3. בשדה **Root Directory** לחצו Edit ובחרו `agent-chat` (חשוב! האפליקציה בתיקיית משנה).
4. תחת **Environment Variables** הוסיפו את 4 המשתנים מהטבלה למעלה.
5. לחצו **Deploy**.

הערה: תשובות של סוכן יכולות לקחת זמן (הרצת כלים וכו'). הקוד מגדיר
`maxDuration = 300` שניות — בתוכנית החינמית של Vercel ודאו ש-Fluid Compute
מופעל (ברירת מחדל בפרויקטים חדשים), אחרת המגבלה נמוכה יותר.
