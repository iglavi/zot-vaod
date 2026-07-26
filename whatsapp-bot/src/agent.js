import Anthropic, { NotFoundError } from "@anthropic-ai/sdk";
import { config } from "./config.js";
import { JsonStore } from "./store.js";
import { logger } from "./logger.js";
import { scheduleReminder } from "./reminders.js";
import { DateTime } from "luxon";

const client = new Anthropic({ apiKey: config.anthropicApiKey });

// מיפוי chatId (מזהה קבוצת וואטסאפ) -> session_id של Managed Agents.
// שומר "זיכרון" נפרד לכל קבוצה גם אחרי הפעלה מחדש של הבוט.
const sessionsStore = new JsonStore(config.sessionsFile, { sessions: {} });

function getStoredSessionId(chatId) {
  return sessionsStore.get("sessions", {})[chatId];
}

function storeSessionId(chatId, sessionId) {
  const sessions = sessionsStore.get("sessions", {});
  sessions[chatId] = sessionId;
  sessionsStore.set("sessions", sessions);
}

async function createSession(chatId) {
  const session = await client.beta.sessions.create({
    agent: config.agentId,
    environment_id: config.environmentId,
    title: `ליצי - ${chatId}`,
  });
  storeSessionId(chatId, session.id);
  logger.info(`נוצר session חדש עבור קבוצה ${chatId}: ${session.id}`);
  return session.id;
}

async function getOrCreateSessionId(chatId) {
  const existing = getStoredSessionId(chatId);
  if (existing) return existing;
  return createSession(chatId);
}

export const SCHEDULE_REMINDER_TOOL = {
  type: "custom",
  name: "schedule_reminder",
  description:
    "קביעת תזכורת עתידית שתישלח לקבוצת הוואטסאפ הזו בתאריך ובשעה שצוינו. " +
    "יש להשתמש בכלי הזה בכל פעם שמבקשים ממך לתזכיר משהו בעתיד (לדוגמה 'תזכיר ביום רביעי ב-18:00 להביא עוגה'). " +
    "עליך לחשב את התאריך הקרוב המתאים (בפורמט YYYY-MM-DD) על סמך התאריך הנוכחי שמופיע בהודעה, ואת השעה בפורמט 24 שעות HH:mm.",
  input_schema: {
    type: "object",
    properties: {
      date: { type: "string", description: "תאריך התזכורת, בפורמט YYYY-MM-DD" },
      time: { type: "string", description: "שעת התזכורת, בפורמט 24 שעות HH:mm" },
      message: { type: "string", description: "תוכן התזכורת שיישלח לקבוצה בהגיע הזמן" },
    },
    required: ["date", "time", "message"],
  },
};

function buildUserMessage({ transcript, senderName, text }) {
  const now = DateTime.now().setZone(config.timezone);
  const nowLabel = now.setLocale("he").toFormat("cccc, d/L/yyyy HH:mm");
  return [
    `[תאריך ושעה נוכחיים: ${nowLabel}, אזור זמן ${config.timezone}]`,
    "[הקשר קבוצתי אחרון - רק לצורך רקע, אין צורך להתייחס לכל שורה]:",
    transcript,
    "",
    "[ההודעה הבאה מופנית אליך ישירות]:",
    `${senderName}: ${text}`,
  ].join("\n");
}

async function handleCustomToolUse(chatId, event) {
  if (event.name !== "schedule_reminder") {
    return { type: "text", text: `שגיאה: כלי לא מוכר: ${event.name}`, isError: true };
  }
  try {
    const { date, time, message } = event.input || {};
    const reminder = scheduleReminder({ chatId, date, time, message });
    return {
      type: "text",
      text: `התזכורת נקבעה בהצלחה ל-${reminder.dueAtIso}.`,
      isError: false,
    };
  } catch (err) {
    logger.error("שגיאה בקביעת תזכורת דרך הסוכן:", err);
    return { type: "text", text: `שגיאה בקביעת התזכורת: ${err.message}`, isError: true };
  }
}

/**
 * מריץ "תור" אחד מול ה-Managed Agent של הקבוצה: פותח stream, שולח הודעת משתמש (כולל
 * הקשר רקע), מטפל בקריאות לכלי התזכורת אם יש, וממתין לתשובה הסופית של הסוכן.
 * מחזיר את טקסט התשובה שיש לשלוח בחזרה לקבוצה.
 */
export async function runTurn(chatId, { senderName, text, transcript }) {
  let sessionId = await getOrCreateSessionId(chatId);

  const userMessage = buildUserMessage({ transcript, senderName, text });

  const runOnce = async (sid) => {
    const stream = await client.beta.sessions.events.stream(sid);

    await client.beta.sessions.events.send(sid, {
      events: [
        {
          type: "user.message",
          content: [{ type: "text", text: userMessage }],
        },
      ],
    });

    const textParts = [];
    for await (const event of stream) {
      switch (event.type) {
        case "agent.message": {
          for (const block of event.content || []) {
            if (block.type === "text") textParts.push(block.text);
          }
          break;
        }
        case "agent.custom_tool_use": {
          const result = await handleCustomToolUse(chatId, event);
          await client.beta.sessions.events.send(sid, {
            events: [
              {
                type: "user.custom_tool_result",
                custom_tool_use_id: event.id,
                content: [{ type: "text", text: result.text }],
                is_error: result.isError,
              },
            ],
          });
          break;
        }
        case "session.error": {
          logger.error(`session.error בסשן ${sid}:`, event.error);
          break;
        }
        case "session.status_idle": {
          if (event.stop_reason?.type !== "requires_action") return textParts.join("\n").trim();
          break;
        }
        case "session.status_terminated": {
          return textParts.join("\n").trim();
        }
        default:
          break;
      }
    }
    return textParts.join("\n").trim();
  };

  try {
    return await runOnce(sessionId);
  } catch (err) {
    if (err instanceof NotFoundError) {
      logger.warn(`ה-session ${sessionId} לא נמצא, יוצר session חדש עבור קבוצה ${chatId}`);
      sessionId = await createSession(chatId);
      return runOnce(sessionId);
    }
    throw err;
  }
}
