import fs from "node:fs";
import path from "node:path";
import { config } from "./config.js";
import { logger } from "./logger.js";

// מגבלת גודל רכה לקובץ זיכרון של קבוצה. כשחורגים ממנה, מבקשים מהסוכן לדחוס.
export const MEMORY_WORD_LIMIT = 2000;

function memoryFilePath(chatId) {
  // מזהה קבוצה כמו 120363297880685416@g.us הופך לשם קובץ בטוח.
  const safeId = chatId.replace(/[^0-9A-Za-z._-]/g, "_");
  return path.join(config.dataDir, `memory-${safeId}.md`);
}

export function readMemory(chatId) {
  try {
    return fs.readFileSync(memoryFilePath(chatId), "utf8");
  } catch {
    return "";
  }
}

function writeMemory(chatId, content) {
  const filePath = memoryFilePath(chatId);
  const tmpPath = `${filePath}.tmp`;
  fs.writeFileSync(tmpPath, content, "utf8");
  fs.renameSync(tmpPath, filePath);
}

export function countWords(text) {
  return text.split(/\s+/).filter(Boolean).length;
}

export function isOverLimit(chatId) {
  return countWords(readMemory(chatId)) > MEMORY_WORD_LIMIT;
}

/**
 * מבצע פעולת עדכון על קובץ הזיכרון של הקבוצה, לפי בקשת הסוכן (הכלי update_memory).
 * פעולות: add (הוספת פריט), update (החלפת טקסט קיים), delete (מחיקת טקסט קיים),
 * rewrite (כתיבה מחדש של כל הקובץ - משמש בעיקר לדחיסה).
 * מחזיר טקסט תוצאה שמוחזר לסוכן.
 */
export function applyMemoryUpdate(chatId, input) {
  const { action, item, old_text: oldText, new_text: newText, content } = input || {};
  const current = readMemory(chatId);

  let next;
  switch (action) {
    case "add": {
      if (!item) throw new Error("לפעולת add חסר השדה item");
      const bullet = item.trim().startsWith("-") ? item.trim() : `- ${item.trim()}`;
      next = current ? `${current.trimEnd()}\n${bullet}\n` : `${bullet}\n`;
      break;
    }
    case "update": {
      if (!oldText || !newText) throw new Error("לפעולת update חסרים old_text ו/או new_text");
      if (!current.includes(oldText)) {
        throw new Error("הטקסט לעדכון (old_text) לא נמצא בקובץ הזיכרון - בדוק את הנוסח המדויק");
      }
      next = current.replace(oldText, newText);
      break;
    }
    case "delete": {
      if (!oldText) throw new Error("לפעולת delete חסר השדה old_text");
      if (!current.includes(oldText)) {
        throw new Error("הטקסט למחיקה (old_text) לא נמצא בקובץ הזיכרון - בדוק את הנוסח המדויק");
      }
      // מוחקים את השורה שמכילה את הטקסט (ולא רק את הטקסט עצמו), כדי לא להשאיר שורות ריקות.
      next = current
        .split("\n")
        .filter((line) => !line.includes(oldText))
        .join("\n");
      break;
    }
    case "rewrite": {
      if (typeof content !== "string") throw new Error("לפעולת rewrite חסר השדה content");
      next = content.trimEnd() + "\n";
      break;
    }
    default:
      throw new Error(`פעולה לא מוכרת: ${action} (אפשרויות: add, update, delete, rewrite)`);
  }

  writeMemory(chatId, next);

  const words = countWords(next);
  logger.info(`עודכן זיכרון לקבוצה ${chatId} (פעולה: ${action}, ${words} מילים)`);

  let result = `הזיכרון עודכן בהצלחה (${words} מילים בקובץ).`;
  if (words > MEMORY_WORD_LIMIT) {
    result +=
      ` שים לב: הקובץ חורג ממגבלת ${MEMORY_WORD_LIMIT} המילים - ` +
      `דחוס אותו בהקדם באמצעות update_memory עם action=rewrite, תוך שמירה על כל המידע החשוב.`;
  }
  return result;
}
