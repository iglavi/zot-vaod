import { config } from "./config.js";
import { logger } from "./logger.js";
import { startWhatsApp } from "./whatsapp.js";
import { startReminderScheduler } from "./reminders.js";

function assertReadyToRun() {
  const missing = [];
  if (!config.agentId) missing.push("AGENT_ID");
  if (!config.environmentId) missing.push("ENVIRONMENT_ID");
  if (missing.length > 0) {
    logger.error(
      `חסרים משתני סביבה: ${missing.join(", ")}. יש להריץ קודם "npm run setup:agent" ` +
        "ולהעתיק את המזהים שמודפסים בסוף, לפי ההוראות ב-README."
    );
    process.exit(1);
  }
  if (!config.whatsappPhoneNumber) {
    logger.warn("WHATSAPP_PHONE_NUMBER לא הוגדר - החיבור הראשוני לוואטסאפ לא יוכל להתחיל.");
  }
  if (config.allowedChatIds.length === 0) {
    logger.warn(
      "ALLOWED_CHAT_IDS ריק - הבוט יתעלם מכל הקבוצות עד שתוסיפו לשם את מזהי הקבוצות המורשות."
    );
  }
}

async function main() {
  assertReadyToRun();
  logger.info(`מפעיל את ${config.botName}...`);

  const whatsapp = await startWhatsApp();
  const stopReminders = startReminderScheduler(whatsapp.sendToChat);

  const shutdown = async (signal) => {
    logger.info(`מתקבל ${signal}, נסגר בצורה מסודרת...`);
    stopReminders();
    await whatsapp.stop();
    process.exit(0);
  };

  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));
}

main().catch((err) => {
  logger.error("שגיאה קריטית באתחול הבוט:", err);
  process.exit(1);
});
