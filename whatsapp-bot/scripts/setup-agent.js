// סקריפט חד-פעמי: יוצר את ה-Managed Agent וה-Environment של ליצי ב-Claude,
// ומדפיס את המזהים (AGENT_ID, ENVIRONMENT_ID) שיש להעתיק למשתני הסביבה של הבוט.
//
// הרצה: ANTHROPIC_API_KEY=sk-ant-... npm run setup:agent
// (או: להריץ אחרי שיצרתם קובץ .env עם ANTHROPIC_API_KEY בתוכו)

import "dotenv/config";
import Anthropic from "@anthropic-ai/sdk";
import { SYSTEM_PROMPT, AGENT_TOOLS } from "../src/agentConfig.js";

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
    description: "בוט וואטסאפ משפחתי שעונה כשפונים אליו בשם, קובע תזכורות וזוכר עובדות משפחתיות.",
    model: "claude-opus-5",
    system: SYSTEM_PROMPT,
    tools: AGENT_TOOLS,
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
