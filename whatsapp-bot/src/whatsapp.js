import { Boom } from "@hapi/boom";
import pino from "pino";
import makeWASocket, {
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason,
  jidNormalizedUser,
  Browsers,
  downloadMediaMessage,
} from "@whiskeysockets/baileys";
import {
  config,
  isChatAllowed,
  TRIGGER_KEYWORDS,
  HUMAN_NAMES,
  CONTINUATION_WINDOW_MS,
} from "./config.js";
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

// סוגי קבצים שהסוכן יכול "לראות" בפועל (Claude תומך בתמונות ומסמכי PDF, לא בווידאו/אודיו).
const SUPPORTED_IMAGE_MIME_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const MAX_MEDIA_BYTES = 15 * 1024 * 1024; // מגבלה נדיבה כדי לא לשלוח קבצים ענקיים לסוכן

function getSupportedMediaKind(message) {
  const imageMimetype = message?.imageMessage?.mimetype;
  if (imageMimetype && SUPPORTED_IMAGE_MIME_TYPES.includes(imageMimetype)) {
    return { kind: "image", mimeType: imageMimetype };
  }
  const documentMimetype = message?.documentMessage?.mimetype;
  if (documentMimetype === "application/pdf") {
    return { kind: "document", mimeType: documentMimetype };
  }
  return null;
}

/** מוריד תמונה/PDF נתמכים מהודעת וואטסאפ ומחזיר תוכן ב-base64, מוכן לצירוף להודעה לסוכן. */
async function downloadSupportedMedia(sock, msg) {
  const info = getSupportedMediaKind(msg.message);
  if (!info) return null;

  try {
    const buffer = await downloadMediaMessage(msg, "buffer", {}, {
      logger: baileysLogger,
      reuploadRequest: sock.updateMediaMessage,
    });
    if (buffer.byteLength > MAX_MEDIA_BYTES) {
      logger.warn(`קובץ שהתקבל גדול מדי (${buffer.byteLength} bytes) - מדלגים על צירוף לסוכן`);
      return null;
    }
    return { kind: info.kind, mimeType: info.mimeType, base64: buffer.toString("base64") };
  } catch (err) {
    logger.error("הורדת קובץ מוואטסאפ נכשלה:", err);
    return null;
  }
}

function getSenderName(msg) {
  if (msg.pushName) return msg.pushName;
  const jid = msg.key.participant || msg.key.remoteJid || "";
  return jid.split("@")[0];
}

// בדיקת טקסט זולה וחד-משמעית (startsWith) - לא ניחוש לפי הקשר.
function startsWithTriggerKeyword(text) {
  const trimmed = text.trim();
  return TRIGGER_KEYWORDS.some((kw) => trimmed.startsWith(kw));
}

function startsWithHumanName(text) {
  const trimmed = text.trim();
  return HUMAN_NAMES.some((name) => trimmed.startsWith(name));
}

export async function startWhatsApp() {
  let stopped = false;
  let currentSock = null;
  const seenUnknownChats = new Set();
  // chatId -> זמן (ms) של התשובה האחרונה של ליצי, לצורך חלון "המשך שיחה" קצר.
  const lastBotReplyAt = new Map();

  async function connect() {
    const { state, saveCreds } = await useMultiFileAuthState(config.authDir);
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
      version,
      auth: state,
      logger: baileysLogger,
      printQRInTerminal: false,
      // חתימת דפדפן "מוכרת" (במקום מחרוזת מותאמת אישית) - יציבה יותר עבור זרימת קוד ההתאמה.
      browser: Browsers.ubuntu("Chrome"),
    });
    currentSock = sock;

    if (!sock.authState.creds.registered && !config.whatsappPhoneNumber) {
      logger.error(
        "אין עדיין חיבור לוואטסאפ ולא הוגדר WHATSAPP_PHONE_NUMBER. הגדירו את משתנה הסביבה ואתחלו מחדש."
      );
    }

    let pairingCodeRequested = false;

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", (update) => {
      const { connection, lastDisconnect, qr } = update;

      // בדיוק כמו בדוגמה הרשמית של Baileys: מבקשים קוד התאמה רק כשהסוקט מאותת
      // שהוא מוכן לכך (אירוע qr), ולא בטיימר שרירותי - כדי לא "לפספס" את חלון הזמן הנכון.
      if (qr && config.whatsappPhoneNumber && !sock.authState.creds.registered && !pairingCodeRequested) {
        pairingCodeRequested = true;
        sock
          .requestPairingCode(config.whatsappPhoneNumber)
          .then((code) => {
            logger.info("=".repeat(50));
            logger.info(`קוד ההתאמה (Pairing Code) שלך: ${code}`);
            logger.info("בטלפון: הגדרות -> מכשירים מקושרים -> קישור מכשיר -> קישור עם מספר טלפון, והזינו את הקוד.");
            logger.info("=".repeat(50));
          })
          .catch((err) => {
            pairingCodeRequested = false;
            logger.error("קבלת קוד ההתאמה נכשלה:", err);
          });
      }

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

    const text = extractMessageText(msg.message) || "";
    const hasSupportedMedia = Boolean(getSupportedMediaKind(msg.message));
    const senderName = getSenderName(msg);

    if (!text && !hasSupportedMedia) {
      const note = briefMediaNote(msg.message);
      if (note) messageBuffer.add(chatId, { sender: senderName, text: note, timestamp: Date.now() });
      return;
    }

    // תמונה/PDF עם כיתוב מטופלים כמו טקסט רגיל לצורך זיהוי פנייה (הכיתוב נבדק כרגיל);
    // תמונה/PDF בלי כיתוב עדיין יכולים "לספור" כהמשך שיחה בתוך החלון הקצר.
    const mediaNote = hasSupportedMedia ? briefMediaNote(msg.message) : null;
    const bufferText = mediaNote ? (text ? `${mediaNote} ${text}` : mediaNote) : text;

    const mentionedJids = msg.message?.extendedTextMessage?.contextInfo?.mentionedJid || [];
    const botJid = sock.user?.id ? jidNormalizedUser(sock.user.id) : null;
    const isTagged = Boolean(botJid) && mentionedJids.some((j) => jidNormalizedUser(j) === botJid);
    const isAddressedByName = text.includes(config.botName);
    const isKeywordTriggered = startsWithTriggerKeyword(text);

    const lastReplyAt = lastBotReplyAt.get(chatId);
    const withinContinuationWindow =
      Boolean(lastReplyAt) && Date.now() - lastReplyAt < CONTINUATION_WINDOW_MS;
    const isContinuation = withinContinuationWindow && !startsWithHumanName(text);

    const isAddressed = isTagged || isAddressedByName || isKeywordTriggered || isContinuation;

    if (!isAddressed) {
      messageBuffer.add(chatId, { sender: senderName, text: bufferText, timestamp: Date.now() });
      return;
    }

    logger.info(`[${chatId}] פנייה מאת ${senderName}: ${bufferText}`);
    const transcript = messageBuffer.formatTranscript(chatId);
    // ההודעה המפנה עצמה נכנסת גם היא לזיכרון הרקע (כדי שהשיחה תישאר רציפה בסיכומים עתידיים)
    messageBuffer.add(chatId, { sender: senderName, text: bufferText, timestamp: Date.now() });

    const media = hasSupportedMedia ? await downloadSupportedMedia(sock, msg) : null;

    try {
      await sock.sendPresenceUpdate("composing", chatId).catch(() => {});
      const reply = await runTurn(chatId, { senderName, text, transcript, media });
      if (reply) {
        await sock.sendMessage(chatId, { text: reply });
        messageBuffer.add(chatId, { sender: config.botName, text: reply, timestamp: Date.now() });
        lastBotReplyAt.set(chatId, Date.now());
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
    stop: async () => {
      stopped = true;
      // סגירה מסודרת של חיבור הוואטסאפ (במקום שהתהליך פשוט ייהרג) - בלי זה, וואטסאפ
      // עלול לראות את זה כניתוק "מלוכלך" ולסרב לחיבור החוזר הבא (session conflict / נותקת).
      if (currentSock) {
        try {
          currentSock.end(undefined);
        } catch (err) {
          logger.warn("שגיאה בסגירה מסודרת של חיבור הוואטסאפ:", err);
        }
      }
      // רגע קטן כדי לתת ל"פריים" הסגירה לצאת בפועל ברשת לפני שהתהליך נסגר.
      await new Promise((resolve) => setTimeout(resolve, 500));
    },
  };
}
