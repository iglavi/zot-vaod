import { config } from "./config.js";
import { logger } from "./logger.js";
import { scheduleReminder } from "./reminders.js";
import { readMemory, applyMemoryUpdate, isOverLimit, getMemoryWordLimit } from "./memory.js";
import { sendEmail } from "./email.js";
import { mediaToContentBlocks } from "./mediaContent.js";
import { createSessionRuntime } from "./agentRuntime.js";
import { ENHANCED_GROUP_INSTRUCTIONS } from "./agentConfig.js";
import { searchDriveFiles, readDriveFile, writeDriveFile } from "./googleDrive.js";
import { DateTime } from "luxon";

const runtime = createSessionRuntime({
  name: "ליצי",
  agentId: config.agentId,
  environmentId: config.environmentId,
  sessionsFile: config.sessionsFile,
});

function buildUserMessage({ chatId, transcript, senderName, text, hasMedia }) {
  const now = DateTime.now().setZone(config.timezone);
  const nowLabel = now.setLocale("he").toFormat("cccc, d/L/yyyy HH:mm");

  const memory = readMemory(chatId);
  const parts = [
    `[תאריך ושעה נוכחיים: ${nowLabel}, אזור זמן ${config.timezone}]`,
    "[זיכרון ארוך-טווח של הקבוצה - עובדות שנשמרו משיחות קודמות]:",
    memory.trim() || "(הזיכרון עדיין ריק)",
  ];

  if (isOverLimit(chatId)) {
    parts.push(
      `[שים לב: קובץ הזיכרון חורג ממגבלת ${getMemoryWordLimit(chatId)} המילים - אחרי שתעני על ההודעה, ` +
        "דחסי אותו באמצעות update_memory עם action=rewrite, תוך שמירה על כל המידע החשוב]"
    );
  }

  if (config.enhancedChatIds.includes(chatId)) {
    parts.push("", ENHANCED_GROUP_INSTRUCTIONS);
  }

  parts.push(
    "",
    "[הקשר קבוצתי אחרון - רק לצורך רקע, אין צורך להתייחס לכל שורה]:",
    transcript,
    "",
    "[ההודעה הבאה מופנית אליך ישירות - הקובץ המצורף, אם יש, מופיע כתוכן נפרד בהודעה זו]:",
    `${senderName}: ${text || (hasMedia ? "(שלח/ה קובץ, בלי טקסט נלווה)" : "")}`
  );

  return parts.join("\n");
}

async function handleCustomToolUse(chatId, event) {
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
      case "send_email": {
        const { to, subject, body } = event.input || {};
        const result = await sendEmail({ to, subject, body });
        return {
          text: `המייל נשלח בהצלחה אל ${result.recipients.join(", ")}.`,
          isError: false,
        };
      }
      case "search_drive_files": {
        if (!config.enhancedChatIds.includes(chatId)) {
          return { text: "כלי זה זמין רק בקבוצה הייעודית למחקר.", isError: true };
        }
        const { query } = event.input || {};
        const files = await searchDriveFiles(query);
        if (files.length === 0) {
          return { text: `לא נמצאו קבצים ששותפו עם הבוט שתואמים ל-"${query}".`, isError: false };
        }
        const list = files
          .map((f) => `- ${f.name} (${f.mimeType}) - עודכן ${f.modifiedTime} - id: ${f.id}`)
          .join("\n");
        return { text: `נמצאו ${files.length} קבצים:\n${list}`, isError: false };
      }
      case "read_drive_file": {
        if (!config.enhancedChatIds.includes(chatId)) {
          return { text: "כלי זה זמין רק בקבוצה הייעודית למחקר.", isError: true };
        }
        const { file_id: fileId } = event.input || {};
        const { name, media } = await readDriveFile(fileId);
        return {
          content: [{ type: "text", text: `[קובץ מגוגל דרייב: ${name}]` }, ...mediaToContentBlocks(media)],
          isError: false,
        };
      }
      case "write_drive_file": {
        if (!config.enhancedChatIds.includes(chatId)) {
          return { text: "כלי זה זמין רק בקבוצה הייעודית למחקר.", isError: true };
        }
        const { file_name: fileName, content } = event.input || {};
        const file = await writeDriveFile(fileName, content);
        return { text: `הקובץ "${file.name}" נשמר בהצלחה בגוגל דרייב.`, isError: false };
      }
      default:
        return { text: `שגיאה: כלי לא מוכר: ${event.name}`, isError: true };
    }
  } catch (err) {
    logger.error(`שגיאה בהפעלת הכלי ${event.name}:`, err);
    return { text: `שגיאה בהפעלת ${event.name}: ${err.message}`, isError: true };
  }
}

/**
 * מריץ "תור" אחד מול ה-Managed Agent של הקבוצה: בונה את תוכן ההודעה (כולל זיכרון
 * ארוך-טווח, הקשר רקע, וקובץ מצורף אם יש), ומעביר ל-runtime המשותף.
 */
export async function runTurn(chatId, { senderName, text, transcript, media }) {
  const userMessage = buildUserMessage({ chatId, transcript, senderName, text, hasMedia: Boolean(media) });
  const content = [...mediaToContentBlocks(media), { type: "text", text: userMessage }];

  return runtime.runTurn(chatId, {
    content,
    title: `ליצי - ${chatId}`,
    toolHandler: (event) => handleCustomToolUse(chatId, event),
  });
}
