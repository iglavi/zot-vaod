import Anthropic, { NotFoundError } from "@anthropic-ai/sdk";
import { config } from "./config.js";
import { JsonStore } from "./store.js";
import { logger } from "./logger.js";

const client = new Anthropic({ apiKey: config.anthropicApiKey });

/**
 * מפעל "runtime" גנרי לניהול שיחה מול Managed Agent אחד: session נפרד לכל chatId
 * (נשמר בקובץ משלו), זיהוי גרסת סוכן חדשה, ולולאת stream/tool-use משותפת.
 * כל "בוט" (ליצי, חבר וכו') מביא רק את הפרטים הספציפיים לו: agentId, environmentId,
 * קובץ ה-sessions, ובכל תור - את תוכן ההודעה ומטפל הכלים המתאימים.
 */
export function createSessionRuntime({ name, agentId, environmentId, sessionsFile }) {
  const sessionsStore = new JsonStore(sessionsFile, { sessions: {} });

  function getStoredSessionId(chatId) {
    return sessionsStore.get("sessions", {})[chatId];
  }

  function storeSessionId(chatId, sessionId) {
    const sessions = sessionsStore.get("sessions", {});
    sessions[chatId] = sessionId;
    sessionsStore.set("sessions", sessions);
  }

  /**
   * session קיים "נעול" על גרסת הסוכן שאיתה נוצר. בעליית התהליך בודקים פעם אחת מהי
   * גרסת הסוכן הנוכחית; אם היא שונה ממה ששמור - מאפסים את מיפוי ה-sessions, כך שכל
   * צ'אט יקבל session חדש עם ההגדרות העדכניות בפנייה הבאה אליו.
   */
  let agentVersionChecked = null;
  async function ensureSessionsMatchAgentVersion() {
    if (!agentVersionChecked) {
      agentVersionChecked = (async () => {
        try {
          const agent = await client.beta.agents.retrieve(agentId);
          const currentVersion = String(agent.version);
          const storedVersion = sessionsStore.get("agentVersion", null);
          if (storedVersion !== currentVersion) {
            if (storedVersion !== null) {
              logger.info(
                `[${name}] זוהתה גרסת סוכן חדשה (${storedVersion} -> ${currentVersion}) - מאפס sessions כדי שהצ'אטים יקבלו את ההגדרות המעודכנות.`
              );
            }
            sessionsStore.set("sessions", {});
            sessionsStore.set("agentVersion", currentVersion);
          }
        } catch (err) {
          logger.warn(`[${name}] בדיקת גרסת הסוכן נכשלה (ממשיכים עם ה-sessions הקיימים):`, err.message);
        }
      })();
    }
    return agentVersionChecked;
  }

  async function createSession(chatId, title) {
    const session = await client.beta.sessions.create({
      agent: agentId,
      environment_id: environmentId,
      title,
    });
    storeSessionId(chatId, session.id);
    logger.info(`[${name}] נוצר session חדש עבור ${chatId}: ${session.id}`);
    return session.id;
  }

  async function getOrCreateSessionId(chatId, title) {
    const existing = getStoredSessionId(chatId);
    if (existing) return existing;
    return createSession(chatId, title);
  }

  /**
   * מריץ "תור" אחד: פותח stream, שולח את content שסופק, מטפל בקריאות לכלים דרך
   * toolHandler(event) -> { text, isError }, וממתין לתשובה הסופית של הסוכן.
   */
  async function runTurn(chatId, { content, title, toolHandler }) {
    await ensureSessionsMatchAgentVersion();
    let sessionId = await getOrCreateSessionId(chatId, title);

    const runOnce = async (sid) => {
      const stream = await client.beta.sessions.events.stream(sid);

      await client.beta.sessions.events.send(sid, {
        events: [{ type: "user.message", content }],
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
            const result = await toolHandler(event);
            // רוב הכלים מחזירים טקסט פשוט (result.text); כלים שצריכים להחזיר מסמך/תמונה
            // בפועל (כמו read_drive_file) מספקים content מוכן מראש (מערך בלוקים).
            const content = result.content ?? [{ type: "text", text: result.text }];
            await client.beta.sessions.events.send(sid, {
              events: [
                {
                  type: "user.custom_tool_result",
                  custom_tool_use_id: event.id,
                  content,
                  is_error: result.isError,
                },
              ],
            });
            break;
          }
          case "session.error": {
            logger.error(`[${name}] session.error בסשן ${sid}:`, event.error);
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
        logger.warn(`[${name}] ה-session ${sessionId} לא נמצא, יוצר session חדש עבור ${chatId}`);
        sessionId = await createSession(chatId, title);
        return runOnce(sessionId);
      }
      throw err;
    }
  }

  return { runTurn };
}
