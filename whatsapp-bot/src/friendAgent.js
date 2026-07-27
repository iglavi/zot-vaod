import { config } from "./config.js";
import { logger } from "./logger.js";
import { scheduleReminder } from "./reminders.js";
import { readMemory, applyMemoryUpdate, isOverLimit, MEMORY_WORD_LIMIT } from "./memory.js";
import { mediaToContentBlocks } from "./mediaContent.js";
import { createSessionRuntime } from "./agentRuntime.js";
import { DateTime } from "luxon";

const runtime = createSessionRuntime({
  name: "חבר",
  agentId: config.friendAgentId,
  environmentId: config.friendEnvironmentId,
  sessionsFile: config.friendSessionsFile,
});

// memory.js מזהה קובץ זיכרון לפי chatId בלבד, ולכן קובץ הזיכרון של השיחה הפרטית
// (memory-<jid מהמספר המורשה>.md) שונה מאליו מקבצי הזיכרון של קבוצות ליצי - אין
// צורך במנגנון נפרד לכך.

function buildFriendUserMessage({ chatId, text, hasMedia }) {
  const now = DateTime.now().setZone(config.timezone);
  const nowLabel = now.setLocale("he").toFormat("cccc, d/L/yyyy HH:mm");

  const memory = readMemory(chatId);
  const parts = [
    `[תאריך ושעה נוכחיים: ${nowLabel}, אזור זמן ${config.timezone}]`,
    "[הזיכרון שלך - תובנות, רעיונות ומפת קשרים שנשמרו משיחות קודמות]:",
    memory.trim() || "(הזיכרון עדיין ריק)",
  ];

  if (isOverLimit(chatId)) {
    parts.push(
      `[שים לב: קובץ הזיכרון חורג ממגבלת ${MEMORY_WORD_LIMIT} המילים - אחרי שתעני על ההודעה, ` +
        "דחסי אותו באמצעות update_memory עם action=rewrite, תוך שמירה על כל המידע החשוב]"
    );
  }

  parts.push("", `המשתמש/ת: ${text || (hasMedia ? "(שלח/ה קובץ, בלי טקסט נלווה)" : "")}`);

  return parts.join("\n");
}

async function handleFriendToolUse(chatId, event) {
  try {
    switch (event.name) {
      case "schedule_reminder": {
        const { date, time, message } = event.input || {};
        const reminder = scheduleReminder({ chatId, date, time, message });
        return { text: `התזכורת נקבעה בהצלחה ל-${reminder.dueAtIso}.`, isError: false };
      }
      case "update_memory": {
        const result = applyMemoryUpdate(chatId, event.input);
        return { text: result, isError: false };
      }
      default:
        return { text: `שגיאה: כלי לא מוכר: ${event.name}`, isError: true };
    }
  } catch (err) {
    logger.error(`שגיאה בהפעלת הכלי ${event.name} (חבר):`, err);
    return { text: `שגיאה בהפעלת ${event.name}: ${err.message}`, isError: true };
  }
}

/** מריץ "תור" אחד מול סוכן "חבר" - שיחה פרטית 1:1, בלי הקשר רקע/תמליל קבוצתי. */
export async function runFriendTurn(chatId, { text, media }) {
  const userMessage = buildFriendUserMessage({ chatId, text, hasMedia: Boolean(media) });
  const content = [...mediaToContentBlocks(media), { type: "text", text: userMessage }];

  return runtime.runTurn(chatId, {
    content,
    title: `חבר - ${chatId}`,
    toolHandler: (event) => handleFriendToolUse(chatId, event),
  });
}
