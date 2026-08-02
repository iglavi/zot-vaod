import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

function Code({ children }: { children: string }) {
  return (
    <pre className="bg-cream border border-border rounded-lg p-4 text-xs overflow-x-auto text-left" dir="ltr">
      <code>{children}</code>
    </pre>
  );
}

function Endpoint({
  method,
  path,
  children,
}: {
  method: string;
  path: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card p-5 space-y-3">
      <div className="flex items-center gap-2 flex-wrap" dir="ltr">
        <span className="bg-green-700 text-white text-xs font-mono rounded px-2 py-1">{method}</span>
        <span className="font-mono text-sm text-ink">{path}</span>
      </div>
      {children}
    </div>
  );
}

export const metadata = {
  title: "תיעוד ה-API הציבורי | גילוי נאות",
  description: "תיעוד נקודות הקצה (API) הציבוריות של גילוי נאות - חיפוש, חיפוש חכם (AI) ונתוני כיסוי.",
};

export default function DocsPage() {
  return (
    <>
      <Header active="/docs" />
      <main id="main-content" className="container-page py-16 max-w-3xl">
        <h1 className="font-display text-3xl text-green-900 mb-4">ה-API הציבורי</h1>
        <p className="text-sm text-ink/80 leading-relaxed mb-4">
          כל הנתונים הזמינים בחיפוש באתר זמינים גם כ-API ציבורי, חופשי
          לשימוש, ללא צורך במפתח או הרשמה - בדיוק המידע הציבורי הזמין
          ממילא באתרי הרשות השופטת, רק מרוכז ונגיש יותר. מיועד לחוקרים,
          עיתונאים, סטודנטים, ומי שרוצה לבנות כלים משלו מעל המאגר.
        </p>
        <div className="card p-5 mb-8 bg-amber-50 border-amber-200">
          <p className="text-sm text-ink/80 leading-relaxed">
            <strong>ללא הסכם רמת-שירות (SLA):</strong> ה-API הזה משרת גם את
            האתר עצמו, ואין כרגע הבטחת זמינות, תמיכה בגרסאות, או התראה
            מראש על שינויים. שימוש בהיקף גדול (crawling מסיבי) עלול
            להיחסם. לשאלות או בקשות שיתוף-פעולה - ראו פרטי יצירת קשר
            בעמוד <a href="/about" className="underline hover:text-green-900">אודות</a>.
          </p>
        </div>

        <h2 className="text-xl font-semibold text-green-900 mb-3">GET /api/search</h2>
        <p className="text-sm text-ink/80 leading-relaxed mb-4">
          חיפוש מובנה לפי שדות. כל הפרמטרים אופציונליים ומשולבים ב-AND
          (רק תוצאות שתואמות את כל השדות שסופקו).
        </p>
        <Endpoint method="GET" path="/api/search">
          <table className="w-full text-xs text-right border-collapse">
            <thead>
              <tr className="border-b border-border text-muted">
                <th className="py-1.5 pl-2 font-medium">פרמטר</th>
                <th className="py-1.5 pl-2 font-medium">תיאור</th>
              </tr>
            </thead>
            <tbody className="[&_td]:py-1.5 [&_td]:pl-2 [&_td]:align-top">
              <tr><td className="font-mono">name</td><td>שם צד (התאמה בשמות הצדדים)</td></tr>
              <tr><td className="font-mono">judge</td><td>שם שופט/ת</td></tr>
              <tr><td className="font-mono">court_type</td><td>סוג ערכאה (למשל &quot;שלום&quot;, &quot;מחוזי&quot;) - הרשימה זמינה ב-/api/search/options</td></tr>
              <tr><td className="font-mono">city</td><td>עיר/מחוז בית המשפט</td></tr>
              <tr><td className="font-mono">case_number</td><td>מספר תיק (תומך בפורמטים חלקיים)</td></tr>
              <tr><td className="font-mono">free_text</td><td>חיפוש חופשי בטקסט המלא של המסמך</td></tr>
              <tr><td className="font-mono">match_mode</td><td><code>any</code> (ברירת מחדל, כל מילה בנפרד) / <code>exact</code> (ביטוי מדויק) / <code>near</code> (המילים קרובות זו לזו)</td></tr>
              <tr><td className="font-mono">proceeding</td><td>סוג הליך</td></tr>
              <tr><td className="font-mono">case_type</td><td>סוג עניין - הרשימה זמינה ב-/api/search/options</td></tr>
              <tr><td className="font-mono">date_from / date_to</td><td>טווח תאריכים, פורמט <code>YYYY-MM-DD</code></td></tr>
              <tr><td className="font-mono">sort</td><td><code>newest</code> (ברירת מחדל) / <code>oldest</code> / <code>relevance</code> / <code>longest</code></td></tr>
              <tr><td className="font-mono">page</td><td>מספר עמוד (10 תוצאות לעמוד), ברירת מחדל 1</td></tr>
            </tbody>
          </table>
          <div className="text-xs text-muted mt-1">דוגמה:</div>
          <Code>{`GET /api/search?free_text=הפרת+חוזה&court_type=שלום&sort=newest&page=1`}</Code>
          <div className="text-xs text-muted mt-1">תשובה:</div>
          <Code>{`{
  "results": [
    {
      "id": 123456,
      "case_number": "12345-01-24",
      "parties": "פלוני נ' אלמוני",
      "court": "בית משפט השלום בתל אביב-יפו",
      "proceeding": "תביעה אזרחית",
      "case_type": "...",
      "decision_type": "פסק דין",
      "decision_date": "2024-06-01",
      "filed_date": "2024-01-10",
      "judge": "...",
      "pdf_url": "https://.../file.pdf",
      "docx_url": "https://.../file.docx"
    }
  ],
  "total": 42,
  "capped": false,
  "page": 1,
  "per_page": 10
}`}</Code>
          <p className="text-xs text-muted mt-1">
            <code>capped: true</code> אומר שהסינון רחב מדי לספירה מדויקת -{" "}
            <code>total</code> הוא תקרה עליונה (&quot;לפחות X&quot;), לא הספירה
            האמיתית. סננו יותר (למשל הוסיפו תאריכים) לקבלת ספירה מדויקת.
          </p>
        </Endpoint>

        <h2 className="text-xl font-semibold text-green-900 mt-8 mb-3">GET /api/search/options</h2>
        <Endpoint method="GET" path="/api/search/options">
          <p className="text-sm text-ink/80">רשימות הערכים הקיימים בפועל במאגר, לשימוש בתפריטי סינון.</p>
          <Code>{`{ "court_types": ["שלום", "מחוזי", "..."], "case_types": ["...", "..."] }`}</Code>
        </Endpoint>

        <h2 className="text-xl font-semibold text-green-900 mt-8 mb-3">GET /api/coverage</h2>
        <Endpoint method="GET" path="/api/coverage">
          <p className="text-sm text-ink/80">
            נתוני היקף המאגר (ראו גם עמוד <a href="/coverage" className="underline hover:text-green-900">שקיפות המאגר</a>).
          </p>
          <Code>{`{
  "total": 3765568,
  "with_documents": 3765568,
  "by_year": [
    { "label": "עד 1999", "count": 1234 },
    { "label": "2000–2009", "count": 12345 },
    { "label": "2010–2019", "count": 123456 },
    { "label": "2020–2026", "count": 1234567 }
  ],
  "supreme": 50000,
  "general": 3715568
}`}</Code>
        </Endpoint>

        <h2 className="text-xl font-semibold text-green-900 mt-8 mb-3">POST /api/ai</h2>
        <Endpoint method="POST" path="/api/ai">
          <p className="text-sm text-ink/80 leading-relaxed">
            חיפוש חכם בשפה טבעית. תשובה בזרם (Server-Sent Events), לא JSON
            רגיל - מתאים לצריכה מדפדפן; לשימוש תוכנתי יש לקרוא את הגוף כזרם
            טקסט ולפרסר לפי הפורמט של SSE.
          </p>
          <div className="text-xs text-muted mt-1">בקשה:</div>
          <Code>{`POST /api/ai
Content-Type: application/json

{
  "question": "מה נפסק בנוגע להפרת חוזה שכירות?",
  "history": [{ "role": "user", "content": "..." }, { "role": "assistant", "content": "..." }]
}`}</Code>
          <p className="text-xs text-muted mt-1"><code>history</code> אופציונלי - תורות קודמות בשיחה, לשאלות המשך.</p>
          <div className="text-xs text-muted mt-1">אירועי הזרם (כל אחד <code>event: NAME\ndata: {"{...}"}\n\n</code>):</div>
          <table className="w-full text-xs text-right border-collapse">
            <tbody className="[&_td]:py-1.5 [&_td]:pl-2 [&_td]:align-top">
              <tr><td className="font-mono">step</td><td><code>{`{"step": "received"|"analyzing"|"retrieving"|"answering"}`}</code> - התקדמות עיבוד</td></tr>
              <tr><td className="font-mono">sources</td><td><code>{`{"verdicts": [...]}`}</code> - פסקי הדין שהתשובה מבוססת עליהם (אותו מבנה כמו /api/search)</td></tr>
              <tr><td className="font-mono">delta</td><td><code>{`{"text": "..."}`}</code> - חלק מטקסט התשובה (מוזרם token-by-token)</td></tr>
              <tr><td className="font-mono">suggestions</td><td><code>{`{"questions": [...]}`}</code> - עד 3 שאלות המשך מוצעות (לא תמיד נשלח)</td></tr>
              <tr><td className="font-mono">done</td><td>סיום הזרם</td></tr>
              <tr><td className="font-mono">error</td><td><code>{`{"message": "..."}`}</code></td></tr>
            </tbody>
          </table>
          <p className="text-xs text-muted mt-1">
            טקסט התשובה עשוי להכיל תגיות <code>&lt;טענה&gt;...&lt;/טענה&gt;</code> סביב תיאור
            טענות-צד (לצורך הפרדה חזותית באתר מקביעות שיפוטיות) - התעלמו
            מהן או הסירו אם אינן רלוונטיות לשימוש שלכם.
          </p>
        </Endpoint>
      </main>
      <Footer />
    </>
  );
}
