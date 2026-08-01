// עדכון סוכן "חבר" הקיים ב-Claude (system prompt + כלים) לגרסה העדכנית שמוגדרת
// ב-src/friendConfig.js - בלי ליצור סוכן חדש ובלי לשנות את FRIEND_AGENT_ID.
//
// הרצה: npm run update:friend-agent  (דורש ANTHROPIC_API_KEY ו-FRIEND_AGENT_ID ב-.env)

import "dotenv/config";
import Anthropic from "@anthropic-ai/sdk";
import { FRIEND_SYSTEM_PROMPT, FRIEND_TOOLS } from "../src/friendConfig.js";

const apiKey = process.env.ANTHROPIC_API_KEY;
const agentId = process.env.FRIEND_AGENT_ID;

if (!apiKey || !agentId) {
  console.error("חסרים ANTHROPIC_API_KEY ו/או FRIEND_AGENT_ID ב-.env.");
  process.exit(1);
}

const client = new Anthropic({ apiKey });

async function main() {
  const current = await client.beta.agents.retrieve(agentId);
  console.log(`סוכן נוכחי: ${current.name} (גרסה ${current.version})`);

  const updated = await client.beta.agents.update(agentId, {
    version: current.version,
    system: FRIEND_SYSTEM_PROMPT,
    tools: FRIEND_TOOLS,
  });

  if (updated.version === current.version) {
    console.log("לא היה שינוי בהגדרות - הגרסה נשארה זהה.");
  } else {
    console.log(`הסוכן עודכן בהצלחה: גרסה ${current.version} -> ${updated.version}`);
    console.log("אין צורך לשנות משתני סביבה - הבוט יזהה את הגרסה החדשה לבד בפנייה הבאה אליו.");
  }
}

main().catch((err) => {
  console.error("עדכון סוכן חבר נכשל:", err);
  process.exit(1);
});
