import Anthropic, { NotFoundError } from "@anthropic-ai/sdk";
import { config } from "./config.js";
import { JsonStore } from "./store.js";
import { logger } from "./logger.js";
import { scheduleReminder } from "./reminders.js";
import { readMemory, applyMemoryUpdate, isOverLimit, MEMORY_WORD_LIMIT } from "./memory.js";
import { sendEmail } from "./email.js";
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

/**
 * session קיים "נעול" על גרסת הסוכן שאיתה נוצר, ולכן שינוי בהגדרת הסוכן (כלי חדש,
 * system prompt מעודכן) לא מגיע אליו. בעליית התהליך בודקים פעם אחת מהי גרסת הסוכן
 * הנוכחית; אם היא שונה ממה ששמור אצלנו - מאפסים את מיפוי ה-sessions, כך שכל קבוצה
 * תקבל session חדש עם הגרסה העדכנית בפנייה הבאה אליה.
 */
let agentVersionChecked = null;
async function ensureSessionsMatchAgentVersion() {
  if (!agentVersionChecked) {
    agentVersionChecked = (async () => {
      try {
        const agent = await client.beta.agents.retrieve(config.agentId);
        const currentVersion = String(agent.version);
        const storedVersion = sessionsStore.get("agentVersion", null);
        if (storedVersion !== currentVersion) {
          if (storedVersion !== null) {
            logger.info(
              `זוהתה גרסת סוכן חדשה (${storedVersion} -> ${currentVersion}) - מאפס sessions כדי שהקבוצות יקבלו את ההגדרות המעודכנות.`
            );
          }
          sessionsStore.set("sessions", {});
          sessionsStore.set("agentVersion", currentVersion);
        }
      } catch (err) {
        logger.warn("בדיקת גרסת הסוכן נכשלה (ממשיכים עם ה-sessions הקיימים):", err.message);
      }
    })();
  }
  return agentVersionChecked;
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

function buildUserMessage({ chatId, transcript, senderName, text }) {
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
      `[שים לב: קובץ הזיכרון חורג ממגבלת ${MEMORY_WORD_LIMIT} המילים - אחרי שתעני על ההודעה, ` +
        "דחסי אותו באמצעות update_memory עם action=rewrite, תוך שמירה על כל המידע החשוב]"
    );
  }

  parts.push(
    "",
    "[הקשר קבוצתי אחרון - רק לצורך רקע, אין צורך להתייחס לכל שורה]:",
    transcript,
    "",
    "[ההודעה הבאה מופנית אליך ישירות]:",
    `${senderName}: ${text}`
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
      default:
        return { text: `שגיאה: כלי לא מוכר: ${event.name}`, isError: true };
    }
  } catch (err) {
    logger.error(`שגיאה בהפעלת הכלי ${event.name}:`, err);
    return { text: `שגיאה בהפעלת ${event.name}: ${err.message}`, isError: true };
  }
}

/**
 * מריץ "תור" אחד מול ה-Managed Agent של הקבוצה: פותח stream, שולח הודעת משתמש (כולל
 * זיכרון ארוך-טווח והקשר רקע), מטפל בקריאות לכלים (תזכורות, זיכרון) אם יש, וממתין
 * לתשובה הסופית של הסוכן. מחזיר את טקסט התשובה שיש לשלוח בחזרה לקבוצה.
 */
export async function runTurn(chatId, { senderName, text, transcript }) {
  await ensureSessionsMatchAgentVersion();
  let sessionId = await getOrCreateSessionId(chatId);

  const userMessage = buildUserMessage({ chatId, transcript, senderName, text });

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
