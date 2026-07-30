import fs from "node:fs";
import { Boom } from "@hapi/boom";
import pino from "pino";
import mammoth from "mammoth";
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
import { runFriendTurn } from "./friendAgent.js";
import { SUPPORTED_IMAGE_MIME_TYPES, DOCX_MIME_TYPE, isMarkdownFile } from "./mediaContent.js";

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

// וידאו/אודיו/מדבקות/doc ישן אינם נתמכים כלל.
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
  if (documentMimetype === DOCX_MIME_TYPE) {
    return { kind: "docx", mimeType: documentMimetype };
  }
  if (isMarkdownFile({ mimeType: documentMimetype, fileName: message?.documentMessage?.fileName })) {
    return { kind: "markdown", mimeType: documentMimetype };
  }
  return null;
}

// כמה ניתוקים רצופים עם אותו קוד שגיאה, תוך כמה זמן, לפני שמפסיקים לנסות reconnect
// "עיוור" ובמקום זאת מנקים את פרטי ההתחברות השמורים ומבקשים קוד התאמה חדש. חלק
// מקודי הניתוק (כמו 428/408) מחלימים לבד תוך כמה ניסיונות; קודים אחרים (כמו 405)
// לא מחלימים אף פעם - בלי הבלם הזה זו לולאת reconnect אינסופית שרק מציפה לוגים.
const RECONNECT_FAILURE_THRESHOLD = 5;
const RECONNECT_FAILURE_WINDOW_MS = 60 * 1000;

/** מוריד תמונה/PDF/Word/Markdown נתמכים מהודעת וואטסאפ, ומחזיר תוכן מוכן לצירוף להודעה לסוכן. */
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

    if (info.kind === "docx") {
      const { value: text } = await mammoth.extractRawText({ buffer });
      if (!text.trim()) {
        logger.warn("לא נמצא טקסט לחילוץ מקובץ ה-Word");
        return null;
      }
      return { kind: "docx-text", text };
    }

    if (info.kind === "markdown") {
      return { kind: "markdown-text", text: buffer.toString("utf8") };
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
  // מעקב אחרי ניתוקים רצופים באותו קוד שגיאה, לצורך הבלם שמונע לולאת reconnect אינסופית.
  let recentReconnectFailure = null; // { statusCode, count, firstAt }
  const seenUnknownChats = new Set();
  const seenUnauthorizedPrivateNumbers = new Set();
  // chatId -> זמן (ms) של התשובה האחרונה של ליצי, לצורך חלון "המשך שיחה" קצר.
  const lastBotReplyAt = new Map();

  async function connect() {
    const { state, saveCreds } = await useMultiFileAuthState(config.authDir);
    // גרסת פרוטוקול הוואטסאפ מתעדכנת מול השרתים של גוגל וואטסאפ מתישהו לזמן-זמן; אם
    // הגרסה "נתקעת" ישנה, וואטסאפ דוחה כל ניסיון חיבור עם קוד 405 (לא בעיית auth בכלל -
    // ראו baileys-version.json ב-GitHub של הפרויקט). fetchLatestBaileysVersion שולפת את
    // הגרסה העדכנית משם בכל הפעלה; אם השליפה נכשלת (למשל בעיית רשת), היא חוזרת בשקט
    // לגרסה מיושנת שחבויה בחבילה המותקנת - לכן חשוב לרשום ללוג אם זה קרה.
    const { version, isLatest } = await fetchLatestBaileysVersion();
    if (!isLatest) {
      logger.warn(`לא הצלחתי לשלוף את גרסת הפרוטוקול העדכנית של וואטסאפ - משתמש בגרסה מיושנת (${version.join(".")}), עלול לגרום לניתוקים עם קוד 405.`);
    } else {
      logger.info(`גרסת פרוטוקול וואטסאפ: ${version.join(".")}`);
    }

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
        recentReconnectFailure = null;
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

        if (
          recentReconnectFailure?.statusCode === statusCode &&
          Date.now() - recentReconnectFailure.firstAt < RECONNECT_FAILURE_WINDOW_MS
        ) {
          recentReconnectFailure.count += 1;
        } else {
          recentReconnectFailure = { statusCode, count: 1, firstAt: Date.now() };
        }

        if (recentReconnectFailure.count >= RECONNECT_FAILURE_THRESHOLD) {
          // עוצרים לגמרי במקום להמשיך לנסות אוטומטית: ניסיונות reconnect/pairing חוזרים
          // ותכופים הם בדיוק הדפוס שגורם לוואטסאפ לזהות "התנהגות בוטית" ולחסום/לנתק
          // מכשיר ביוזמתה (קוד 401/loggedOut) - המשך ניסיונות אוטומטיים בשלב הזה עלול
          // להחמיר חסימה כזו במקום לפתור אותה. מנקים auth כדי שהניסיון הידני הבא יתחיל
          // נקי, אבל מחכים להפעלה מחדש ידנית (לא מייד, ולא בלולאה).
          logger.error(
            `${recentReconnectFailure.count} ניתוקים רצופים עם קוד ${statusCode} תוך פחות מ-` +
              `${RECONNECT_FAILURE_WINDOW_MS / 1000} שניות - עוצר ניסיונות reconnect אוטומטיים ` +
              "(ניסיונות חוזרים ותכופים מדי עלולים להיראות לוואטסאפ כהתנהגות בוטית ולהחמיר את הבעיה). " +
              "מנקה את תיקיית ההתחברות (DATA_DIR/baileys_auth). מומלץ להמתין קצת (למשל שעה) לפני " +
              "הפעלה מחדש ידנית של השירות לניסיון חיבור נקי עם קוד התאמה חדש."
          );
          recentReconnectFailure = null;
          try {
            fs.rmSync(config.authDir, { recursive: true, force: true });
          } catch (err) {
            logger.warn("מחיקת תיקיית ההתחברות נכשלה:", err.message);
          }
          return;
        }

        logger.warn(
          `החיבור לוואטסאפ נסגר, מתחבר מחדש... ${statusCode || ""} ` +
            `(ניסיון ${recentReconnectFailure.count}/${RECONNECT_FAILURE_THRESHOLD} באותו קוד)`
        );
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
    if (msg.key.fromMe) return;

    if (chatId.endsWith("@s.whatsapp.net")) {
      return handlePrivateMessage(sock, msg, chatId);
    }

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

    // בקבוצות "משודרגות" (בד"כ שיחה ייעודית עם משתמש/ת יחיד/ה) כל הודעה נחשבת פנייה
    // ישירה - בלי תיוג/שם/מילת מפתח - בדיוק כמו שיחה פרטית, כי אין שם "רעש רקע" בין
    // כמה בני אדם לסנן ממנו.
    const isAddressed =
      config.enhancedChatIds.includes(chatId) ||
      isTagged ||
      isAddressedByName ||
      isKeywordTriggered ||
      isContinuation;

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

  /**
   * שיחה פרטית (DM, לא קבוצה) - מנותבת לגמרי לסוכן "חבר", נפרד מליצי.
   *
   * אבטחה קריטית: רק chatId שהוא בדיוק המספר המורשה (FRIEND_ALLOWED_NUMBER) מטופל.
   * כל שיחה פרטית ממספר אחר - מתעלמים לגמרי, בלי שום תגובה ובלי לוג שיכול לחשוף
   * שהבוט בכלל "קיים" עבור מספרים לא מורשים.
   */
  async function handlePrivateMessage(sock, msg, chatId) {
    if (!config.friendAllowedNumber) return; // לא הוגדר - אין למי לענות, שקט מוחלט

    const allowedJid = `${config.friendAllowedNumber}@s.whatsapp.net`;
    if (chatId !== allowedJid) {
      // בלי תגובה לשולח בכל מקרה (שם עובר האבטחה האמיתית) - אבל כן רושמים פעם אחת ללוג
      // הפרטי (נגיש רק לבעלים ב-Railway), כדי שיהיה אפשר לוודא/לתקן את FRIEND_ALLOWED_NUMBER
      // בדיוק כמו מנגנון גילוי הקבוצות הלא-מאושרות.
      if (!seenUnauthorizedPrivateNumbers.has(chatId)) {
        seenUnauthorizedPrivateNumbers.add(chatId);
        logger.info(
          `הודעה פרטית ממספר לא מאושר: ${chatId} (לא תואם ל-FRIEND_ALLOWED_NUMBER הנוכחי - אם זה המספר שלך, ודאו שהוא מוגדר בדיוק כמו הספרות שלפני ה-@ כאן)`
        );
      }
      return;
    }

    const text = extractMessageText(msg.message) || "";
    const hasSupportedMedia = Boolean(getSupportedMediaKind(msg.message));
    if (!text && !hasSupportedMedia) return; // למשל סטיקר/וידאו בלי טקסט - אין מה להעביר

    logger.info(`[${config.friendBotName}] פנייה פרטית: ${text || "(קובץ מצורף)"}`);
    const media = hasSupportedMedia ? await downloadSupportedMedia(sock, msg) : null;

    try {
      await sock.sendPresenceUpdate("composing", chatId).catch(() => {});
      const reply = await runFriendTurn(chatId, { text, media });
      if (reply) await sock.sendMessage(chatId, { text: reply });
    } catch (err) {
      logger.error(`שגיאה בקבלת תשובה מסוכן ${config.friendBotName}:`, err);
      await sock.sendMessage(chatId, { text: "סליחה, נתקלתי בשגיאה 🙏 נסה שוב בעוד רגע." }).catch(() => {});
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
