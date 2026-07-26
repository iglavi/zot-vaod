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

  // דוא"ל: ליצי שולח/ת מתוך כתובת ה-Gmail הזו (אימות מול Gmail SMTP באמצעות App
  // Password - לא הסיסמה הרגילה של החשבון). App Password מוצג עם רווחים לנוחות
  // קריאה; מסירים אותם כאן כדי שלא ישפיעו על האימות מול השרת.
  myEmail: (process.env.GMAIL_ADDRESS || "").trim(),
  gmailAppPassword: (process.env.GMAIL_APP_PASSWORD || "").replace(/\s+/g, ""),
  shaniEmail: (process.env.SHANI_EMAIL || "").trim(),
};

export function isChatAllowed(chatId) {
  return config.allowedChatIds.includes(chatId);
}

// מילות מפתח שמפעילות את ליצי גם בלי תיוג ובלי הזכרת שם, כשההודעה מתחילה בהן
// (אחרי טרים של רווחים). בדיקה זולה וחד-משמעית (startsWith) - לא ניחוש לפי הקשר.
// להוספת/הסרת מילה - פשוט לערוך את הרשימה כאן, בלי לחפש בשאר הקוד.
export const TRIGGER_KEYWORDS = ["תזכיר", "תזכור", "תציע", "תבדוק", "תסכם", "תחשב", "תכתוב"];

// שמות בני האדם בקבוצה. משמש רק כדי לזהות שהודעת-המשך (בתוך חלון השיחה הקצר
// שאחרי תשובה של ליצי) מופנית בפועל לאדם אחר ולא לליצי.
export const HUMAN_NAMES = ["יגאל", "שני"];

// חלון הזמן (מ"ש) שבו הודעה הבאה אחרי תשובה של ליצי נחשבת כהמשך פנייה אליו,
// גם בלי תיוג/שם/מילת מפתח - מתאים לקבוצה קטנה עם שיחה ישירה מולו.
export const CONTINUATION_WINDOW_MS = 2 * 60 * 1000;
