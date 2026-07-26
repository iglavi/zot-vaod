// סקריפט חד-פעמי: יוצר את ה-Managed Agent וה-Environment של ליצי ב-Claude,
// ומדפיס את המזהים (AGENT_ID, ENVIRONMENT_ID) שיש להעתיק למשתני הסביבה של הבוט.
//
// הרצה: ANTHROPIC_API_KEY=sk-ant-... npm run setup:agent
// (או: להריץ אחרי שיצרתם קובץ .env עם ANTHROPIC_API_KEY בתוכו)

import "dotenv/config";
import Anthropic from "@anthropic-ai/sdk";
import { SCHEDULE_REMINDER_TOOL } from "../src/agent.js";

const apiKey = process.env.ANTHROPIC_API_KEY;
if (!apiKey) {
  console.error("חסר ANTHROPIC_API_KEY. הוסיפו אותו לקובץ .env או הריצו עם המשתנה מוגדר.");
  process.exit(1);
}

if ((process.env.AGENT_ID || process.env.ENVIRONMENT_ID) && !process.env.FORCE_RECREATE) {
  console.error(
    "נראה ש-AGENT_ID ו/או ENVIRONMENT_ID כבר מוגדרים ב-.env.\n" +
      "אם בכל זאת רוצים ליצור סוכן וסביבה חדשים (למשל כדי לשנות מודל או system prompt), " +
      "יש להריץ שוב עם FORCE_RECREATE=1. אחרת אין צורך להריץ את הסקריפט הזה שוב."
  );
  process.exit(1);
}

const client = new Anthropic({ apiKey });

const SYSTEM_PROMPT = `את/ה "ליצי" - עוזר/ת משפחתי/ת בקבוצות וואטסאפ, כולל בין השאר קבוצות עם יגאל ושני.

איך לנהוג:
- עני/ה תמיד בעברית בלבד, בטון חם, קליל וממוקד. בלי הקדמות מיותרות ("בטח!", "כמובן!") - ישר לעניין.
- כל הודעה שמגיעה אליך מתחילה בשורת "[תאריך ושעה נוכחיים: ...]" ולאחריה "[הקשר קבוצתי אחרון]" -
  תמליל של ההודעות האחרונות בקבוצה (לא בהכרח פנייה אליך, רק רקע). השתמשי בהקשר הזה כשמבקשים ממך
  סיכום של מה שדובר, אבל אל תתייחסי אליו כאילו כל שורה שם מיועדת לך.
- אחרי זה מופיעה השורה "[ההודעה הבאה מופנית אליך ישירות]" ואז ההודעה שבאמת צריך לענות עליה.
- כשמבקשים ממך לקבוע תזכורת (למשל "תזכיר/י ביום רביעי ב-18:00 להביא עוגה") - חשבי מה התאריך
  הקרוב המתאים ליום שצוין (בהתבסס על התאריך הנוכחי שמופיע בהודעה) והשתמשי בכלי schedule_reminder
  כדי לקבוע אותה. לאחר קביעת התזכורת, אשרי בקצרה לקבוצה מתי היא תישלח.
- אם מבקשים תזכורת בלי לציין שעה, בררי או הניחי שעה סבירה (למשל 09:00) ואמרי זאת בבירור בתשובה.
- שמרי על תשובות קצרות וממוקדות - זו קבוצת וואטסאפ משפחתית, לא מסמך רשמי.
- אין לך גישה לקבצים, קוד או אינטרנט חיצוני מעבר לחיפוש רשת אם הופעל עבורך - השתמשי בו רק כשבאמת נדרש מידע עדכני.`;

async function main() {
  console.log("יוצר Environment...");
  const environment = await client.beta.environments.create({
    name: "litzi-family-bot-env",
    config: {
      type: "cloud",
      networking: { type: "unrestricted" },
    },
  });
  console.log(`Environment נוצר: ${environment.id}`);

  console.log("יוצר Agent...");
  const agent = await client.beta.agents.create({
    name: "ליצי - בוט משפחתי",
    description: "בוט וואטסאפ משפחתי שעונה כשפונים אליו בשם וקובע תזכורות.",
    model: "claude-opus-5",
    system: SYSTEM_PROMPT,
    tools: [
      SCHEDULE_REMINDER_TOOL,
      {
        type: "agent_toolset_20260401",
        default_config: { enabled: false },
        configs: [
          { name: "web_search", enabled: true },
          { name: "web_fetch", enabled: true },
        ],
      },
    ],
  });
  console.log(`Agent נוצר: ${agent.id} (גרסה ${agent.version})`);

  console.log("\n" + "=".repeat(60));
  console.log("הסתיים בהצלחה! הוסיפו את השורות הבאות למשתני הסביבה (.env / Railway Variables):");
  console.log("=".repeat(60));
  console.log(`AGENT_ID=${agent.id}`);
  console.log(`ENVIRONMENT_ID=${environment.id}`);
  console.log("=".repeat(60));
}

main().catch((err) => {
  console.error("משהו השתבש ביצירת הסוכן/הסביבה:", err);
  process.exit(1);
});
