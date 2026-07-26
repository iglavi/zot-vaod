import { randomUUID } from "node:crypto";
import { DateTime } from "luxon";
import { config } from "./config.js";
import { JsonStore } from "./store.js";
import { logger } from "./logger.js";

const store = new JsonStore(config.remindersFile, { reminders: [] });

function getAll() {
  return store.get("reminders", []);
}

function saveAll(list) {
  store.set("reminders", list);
}

/**
 * קובע תזכורת חדשה. date בפורמט YYYY-MM-DD, time בפורמט HH:mm, שניהם לפי אזור הזמן המוגדר.
 * אם התאריך/שעה שחושבו כבר עברו, מניחים שהכוונה לשבוע הבא ומקדמים ב-7 ימים (רשת ביטחון
 * למקרה שהסוכן חישב "יום רביעי הקרוב" והתבלבל).
 */
export function scheduleReminder({ chatId, date, time, message }) {
  if (!chatId || !date || !time || !message) {
    throw new Error("scheduleReminder: חסרים פרטים (chatId/date/time/message)");
  }

  let due = DateTime.fromISO(`${date}T${time}`, { zone: config.timezone });
  if (!due.isValid) {
    throw new Error(`תאריך/שעה לא תקינים: ${date} ${time} (${due.invalidExplanation})`);
  }

  const now = DateTime.now().setZone(config.timezone);
  if (due < now) {
    due = due.plus({ weeks: 1 });
  }

  const reminder = {
    id: randomUUID(),
    chatId,
    message,
    dueAtIso: due.toISO(),
    createdAtIso: now.toISO(),
    sent: false,
  };

  const all = getAll();
  all.push(reminder);
  saveAll(all);

  logger.info(`נקבעה תזכורת #${reminder.id} לקבוצה ${chatId} בתאריך ${due.toFormat("dd/LL/yyyy HH:mm")}`);
  return reminder;
}

export function listUpcomingForChat(chatId) {
  return getAll()
    .filter((r) => r.chatId === chatId && !r.sent)
    .sort((a, b) => a.dueAtIso.localeCompare(b.dueAtIso));
}

function takeDueReminders() {
  const all = getAll();
  const nowIso = DateTime.now().setZone(config.timezone).toISO();
  const due = all.filter((r) => !r.sent && r.dueAtIso <= nowIso);
  if (due.length === 0) return [];

  const dueIds = new Set(due.map((r) => r.id));
  const remaining = all.filter((r) => !dueIds.has(r.id));
  saveAll(remaining);
  return due;
}

/**
 * מפעיל בדיקה תקופתית של תזכורות שהגיע זמנן, ושולח כל אחת דרך sendFn(chatId, text).
 * מחזיר פונקציית עצירה (לניקוי נקי בכיבוי התהליך).
 */
export function startReminderScheduler(sendFn) {
  const tick = async () => {
    let due = [];
    try {
      due = takeDueReminders();
    } catch (err) {
      logger.error("שגיאה בבדיקת תזכורות:", err);
      return;
    }

    for (const reminder of due) {
      try {
        await sendFn(reminder.chatId, `⏰ תזכורת: ${reminder.message}`);
        logger.info(`נשלחה תזכורת #${reminder.id} לקבוצה ${reminder.chatId}`);
      } catch (err) {
        logger.error(`שליחת תזכורת #${reminder.id} נכשלה:`, err);
      }
    }
  };

  const interval = setInterval(tick, config.reminderPollIntervalMs);
  // בדיקה ראשונה מיידית עם עלייה של הבוט, למקרה שהיה כבוי כשתזכורת הייתה אמורה לצאת.
  tick();

  return () => clearInterval(interval);
}
