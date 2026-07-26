import { Boom } from "@hapi/boom";
import pino from "pino";
import makeWASocket, {
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason,
  jidNormalizedUser,
} from "@whiskeysockets/baileys";
import { config, isChatAllowed } from "./config.js";
import { logger } from "./logger.js";
import { messageBuffer } from "./messageBuffer.js";
import { runTurn } from "./agent.js";

// לוגר "שקט" עבור Baileys עצמו - הלוגים היישומיים שלנו עוברים דרך logger.js.
const baileysLogger = pino({ level: process.env.BAILEYS_LOG_LEVEL || "silent" });

function extractMessageText(message) {
  if (!message) return null;
  if (message.conversation) return message.conversation;
  if (message.extendedTextMessage?.text) return message.extendedTextMessage.text;
  if (message.imageMessage?.caption) return message.imageMessage.caption;
  if (message.videoMessage?.caption) return message.videoMessage.caption;
  return null;
}

function briefMediaNote(message) {
  if (message?.imageMessage) return "[שלח/ה תמונה]";
  if (message?.videoMessage) return "[שלח/ה סרטון]";
  if (message?.audioMessage) return "[שלח/ה הודעה קולית]";
  if (message?.stickerMessage) return "[שלח/ה מדבקה]";
  if (message?.documentMessage) return "[שלח/ה קובץ]";
  return null;
}

function getSenderName(msg) {
  if (msg.pushName) return msg.pushName;
  const jid = msg.key.participant || msg.key.remoteJid || "";
  return jid.split("@")[0];
}

export async function startWhatsApp() {
  let stopped = false;
  let currentSock = null;
  const seenUnknownChats = new Set();

  async function connect() {
    const { state, saveCreds } = await useMultiFileAuthState(config.authDir);
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
      version,
      auth: state,
      logger: baileysLogger,
      printQRInTerminal: false,
      browser: ["ליצי", "Chrome", "1.0.0"],
    });
    currentSock = sock;

    if (!sock.authState.creds.registered) {
      if (!config.whatsappPhoneNumber) {
        logger.error(
          "אין עדיין חיבור לוואטסאפ ולא הוגדר WHATSAPP_PHONE_NUMBER. הגדירו את משתנה הסביבה ואתחלו מחדש."
        );
      } else {
        setTimeout(async () => {
          try {
            const code = await sock.requestPairingCode(config.whatsappPhoneNumber);
            logger.info("=".repeat(50));
            logger.info(`קוד ההתאמה (Pairing Code) שלך: ${code}`);
            logger.info("בטלפון: הגדרות -> מכשירים מקושרים -> קישור מכשיר -> קישור עם מספר טלפון, והזינו את הקוד.");
            logger.info("=".repeat(50));
          } catch (err) {
            logger.error("קבלת קוד ההתאמה נכשלה:", err);
          }
        }, 3000);
      }
    }

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", (update) => {
      const { connection, lastDisconnect } = update;
      if (connection === "open") {
        logger.info("החיבור לוואטסאפ פעיל ✅");
      } else if (connection === "close") {
        const statusCode = lastDisconnect?.error instanceof Boom
          ? lastDisconnect.error.output?.statusCode
          : undefined;
        const loggedOut = statusCode === DisconnectReason.loggedOut;

        if (loggedOut) {
          logger.error(
            "החיבור לוואטסאפ נותק (נותקת מהמכשיר). יש למחוק את תיקיית ההתחברות (DATA_DIR/baileys_auth) ולהתחבר מחדש עם קוד התאמה חדש."
          );
          return;
        }

        logger.warn("החיבור לוואטסאפ נסגר, מתחבר מחדש...", statusCode || "");
        if (!stopped) setTimeout(connect, 2000);
      }
    });

    sock.ev.on("messages.upsert", async ({ messages, type }) => {
      if (type !== "notify") return;
      for (const msg of messages) {
        try {
          await handleIncomingMessage(sock, msg);
        } catch (err) {
          logger.error("שגיאה בטיפול בהודעה נכנסת:", err);
        }
      }
    });

    return sock;
  }

  async function handleIncomingMessage(sock, msg) {
    const chatId = msg.key.remoteJid;
    if (!chatId || chatId === "status@broadcast") return;
    if (!isChatAllowed(chatId)) {
      // מזהה קבוצה שעדיין לא ברשימה המורשית - מדפיסים פעם אחת ללוג כדי שיהיה קל להעתיק
      // אותו ל-ALLOWED_CHAT_IDS (זו הדרך הפשוטה ביותר לגלות מהו ה-JID של קבוצה).
      if (chatId.endsWith("@g.us") && !seenUnknownChats.has(chatId)) {
        seenUnknownChats.add(chatId);
        logger.info(
          `הודעה מקבוצה לא מאושרת: ${chatId} (כדי לאשר את הקבוצה, הוסיפו את המזהה הזה ל-ALLOWED_CHAT_IDS)`
        );
      }
      return;
    }
    if (msg.key.fromMe) return;

    const text = extractMessageText(msg.message);
    const senderName = getSenderName(msg);

    if (!text) {
      const note = briefMediaNote(msg.message);
      if (note) messageBuffer.add(chatId, { sender: senderName, text: note, timestamp: Date.now() });
      return;
    }

    const mentionedJids = msg.message?.extendedTextMessage?.contextInfo?.mentionedJid || [];
    const botJid = sock.user?.id ? jidNormalizedUser(sock.user.id) : null;
    const isTagged = Boolean(botJid) && mentionedJids.some((j) => jidNormalizedUser(j) === botJid);
    const isAddressedByName = text.includes(config.botName);

    if (!isTagged && !isAddressedByName) {
      messageBuffer.add(chatId, { sender: senderName, text, timestamp: Date.now() });
      return;
    }

    logger.info(`[${chatId}] פנייה מאת ${senderName}: ${text}`);
    const transcript = messageBuffer.formatTranscript(chatId);
    // ההודעה המפנה עצמה נכנסת גם היא לזיכרון הרקע (כדי שהשיחה תישאר רציפה בסיכומים עתידיים)
    messageBuffer.add(chatId, { sender: senderName, text, timestamp: Date.now() });

    try {
      await sock.sendPresenceUpdate("composing", chatId).catch(() => {});
      const reply = await runTurn(chatId, { senderName, text, transcript });
      if (reply) {
        await sock.sendMessage(chatId, { text: reply });
        messageBuffer.add(chatId, { sender: config.botName, text: reply, timestamp: Date.now() });
      }
    } catch (err) {
      logger.error("שגיאה בקבלת תשובה מהסוכן:", err);
      await sock
        .sendMessage(chatId, { text: "סליחה, נתקלתי בשגיאה 🙏 נסו שוב בעוד רגע." })
        .catch(() => {});
    } finally {
      await sock.sendPresenceUpdate("paused", chatId).catch(() => {});
    }
  }

  await connect();

  return {
    sendToChat: async (chatId, text) => {
      if (!currentSock) throw new Error("הוואטסאפ עדיין לא מחובר");
      await currentSock.sendMessage(chatId, { text });
      messageBuffer.add(chatId, { sender: config.botName, text, timestamp: Date.now() });
    },
    stop: () => {
      stopped = true;
    },
  };
}
