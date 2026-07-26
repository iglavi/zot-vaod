// עדכון הסוכן הקיים ב-Claude (system prompt + כלים) לגרסה העדכנית שמוגדרת
// ב-src/agentConfig.js - בלי ליצור סוכן חדש ובלי לשנות את AGENT_ID.
//
// הרצה: npm run update:agent  (דורש ANTHROPIC_API_KEY ו-AGENT_ID ב-.env)

import "dotenv/config";
import Anthropic from "@anthropic-ai/sdk";
import { SYSTEM_PROMPT, AGENT_TOOLS } from "../src/agentConfig.js";

const apiKey = process.env.ANTHROPIC_API_KEY;
const agentId = process.env.AGENT_ID;

if (!apiKey || !agentId) {
  console.error("חסרים ANTHROPIC_API_KEY ו/או AGENT_ID ב-.env.");
  process.exit(1);
}

const client = new Anthropic({ apiKey });

async function main() {
  const current = await client.beta.agents.retrieve(agentId);
  console.log(`סוכן נוכחי: ${current.name} (גרסה ${current.version})`);

  const updated = await client.beta.agents.update(agentId, {
    version: current.version,
    system: SYSTEM_PROMPT,
    tools: AGENT_TOOLS,
  });

  if (updated.version === current.version) {
    console.log("לא היה שינוי בהגדרות - הגרסה נשארה זהה.");
  } else {
    console.log(`הסוכן עודכן בהצלחה: גרסה ${current.version} -> ${updated.version}`);
    console.log("אין צורך לשנות משתני סביבה - הבוט יזהה את הגרסה החדשה לבד בעלייה הבאה שלו.");
  }
}

main().catch((err) => {
  console.error("עדכון הסוכן נכשל:", err);
  process.exit(1);
});
