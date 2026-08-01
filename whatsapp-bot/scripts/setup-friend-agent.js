// סקריפט חד-פעמי: יוצר את ה-Managed Agent וה-Environment של סוכן "חבר" (שיחה
// פרטית/DM, נפרד לגמרי מליצי) ב-Claude, ומדפיס את המזהים (FRIEND_AGENT_ID,
// FRIEND_ENVIRONMENT_ID) שיש להעתיק למשתני הסביבה של הבוט.
//
// הרצה: npm run setup:friend-agent
// (אחרי שיצרתם קובץ .env עם ANTHROPIC_API_KEY בתוכו)

import "dotenv/config";
import Anthropic from "@anthropic-ai/sdk";
import { FRIEND_SYSTEM_PROMPT, FRIEND_TOOLS } from "../src/friendConfig.js";

const apiKey = process.env.ANTHROPIC_API_KEY;
if (!apiKey) {
  console.error("חסר ANTHROPIC_API_KEY. הוסיפו אותו לקובץ .env או הריצו עם המשתנה מוגדר.");
  process.exit(1);
}

// מתעלם מערכי הדוגמה שמגיעים מ-.env.example בהעתקה ישירה (כמו "agent_..."), כדי
// שלא "יחשבו" שהסוכן כבר קיים כשבפועל רק הועתקה התבנית בלי מילוי.
function isConfigured(value) {
  return Boolean(value) && !value.includes("...");
}

if ((isConfigured(process.env.FRIEND_AGENT_ID) || isConfigured(process.env.FRIEND_ENVIRONMENT_ID)) && !process.env.FORCE_RECREATE) {
  console.error(
    "נראה ש-FRIEND_AGENT_ID ו/או FRIEND_ENVIRONMENT_ID כבר מוגדרים ב-.env.\n" +
      "אם בכל זאת רוצים ליצור סוכן וסביבה חדשים, יש להריץ שוב עם FORCE_RECREATE=1. " +
      "אחרת אין צורך להריץ את הסקריפט הזה שוב - לעדכון system prompt/כלים של סוכן קיים " +
      "יש להשתמש ב-npm run update:friend-agent."
  );
  process.exit(1);
}

const client = new Anthropic({ apiKey });

async function main() {
  console.log("יוצר Environment...");
  const environment = await client.beta.environments.create({
    name: "friend-agent-env",
    config: {
      type: "cloud",
      networking: { type: "unrestricted" },
    },
  });
  console.log(`Environment נוצר: ${environment.id}`);

  console.log("יוצר Agent...");
  const agent = await client.beta.agents.create({
    name: "חבר - עוזר אישי פרטי",
    description: "עוזר אישי פרטי בשיחת וואטסאפ אחד-על-אחד, נפרד לגמרי מבוט הקבוצה המשפחתית.",
    model: "claude-opus-5",
    system: FRIEND_SYSTEM_PROMPT,
    tools: FRIEND_TOOLS,
  });
  console.log(`Agent נוצר: ${agent.id} (גרסה ${agent.version})`);

  console.log("\n" + "=".repeat(60));
  console.log("הסתיים בהצלחה! הוסיפו את השורות הבאות למשתני הסביבה (.env / Railway Variables):");
  console.log("=".repeat(60));
  console.log(`FRIEND_AGENT_ID=${agent.id}`);
  console.log(`FRIEND_ENVIRONMENT_ID=${environment.id}`);
  console.log("=".repeat(60));
  console.log(
    "\nאל תשכחו להגדיר גם FRIEND_ALLOWED_NUMBER - המספר היחיד שמורשה לפתוח שיחה פרטית עם הסוכן הזה."
  );
}

main().catch((err) => {
  console.error("משהו השתבש ביצירת הסוכן/הסביבה:", err);
  process.exit(1);
});
