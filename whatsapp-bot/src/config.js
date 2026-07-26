import "dotenv/config";
import path from "node:path";
import fs from "node:fs";

function required(name, { allowEmptyInSetup = false } = {}) {
  const value = process.env[name];
  if (!value && !allowEmptyInSetup) {
    throw new Error(`חסר משתנה סביבה נדרש: ${name}. בדקו את קובץ .env / את הגדרות ה-Environment ב-Railway.`);
  }
  return value;
}

const dataDir = path.resolve(process.env.DATA_DIR || "./data");
fs.mkdirSync(dataDir, { recursive: true });

const allowedChatIds = (process.env.ALLOWED_CHAT_IDS || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

export const config = {
  anthropicApiKey: required("ANTHROPIC_API_KEY"),
  agentId: process.env.AGENT_ID || "",
  environmentId: process.env.ENVIRONMENT_ID || "",

  whatsappPhoneNumber: (process.env.WHATSAPP_PHONE_NUMBER || "").replace(/[^0-9]/g, ""),
  botName: process.env.BOT_NAME || "ליצי",

  allowedChatIds,

  dataDir,
  authDir: path.join(dataDir, "baileys_auth"),
  sessionsFile: path.join(dataDir, "sessions.json"),
  remindersFile: path.join(dataDir, "reminders.json"),

  timezone: process.env.TIMEZONE || "Asia/Jerusalem",
  messageBufferSize: Number(process.env.MESSAGE_BUFFER_SIZE || 200),

  reminderPollIntervalMs: Number(process.env.REMINDER_POLL_INTERVAL_MS || 20_000),
};

export function isChatAllowed(chatId) {
  return config.allowedChatIds.includes(chatId);
}
