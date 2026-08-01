import nodemailer from "nodemailer";
import { config } from "./config.js";
import { logger } from "./logger.js";

const SUBJECT_SUFFIX = "מייל מליצי הבוט";

let transporter = null;
function getTransporter() {
  if (!transporter) {
    transporter = nodemailer.createTransport({
      service: "gmail",
      auth: { user: config.myEmail, pass: config.gmailAppPassword },
    });
  }
  return transporter;
}

/** ממפה את התוויות הקבועות שהסוכן שולח (לא כתובות מייל בפועל) לכתובות האמיתיות. */
function labelToAddress(label) {
  if (label === "me") return config.myEmail;
  if (label === "shani") return config.shaniEmail;
  return null;
}

/**
 * שולח מייל דרך Gmail SMTP מכתובת הבעלים (config.myEmail), רק לנמענים ברשימה
 * הסגורה (הבעלים ו/או שני) - כל כתובת אחרת נדחית לפני שנשלח משהו.
 * מוסיף אוטומטית את הסיומת הקבועה "מייל מליצי הבוט" לנושא.
 */
export async function sendEmail({ to, subject, body }) {
  if (!config.myEmail || !config.gmailAppPassword) {
    throw new Error("שליחת מייל לא מוגדרת - חסרים GMAIL_ADDRESS ו/או GMAIL_APP_PASSWORD");
  }
  if (!Array.isArray(to) || to.length === 0) {
    throw new Error("חסר שדה to (רשימת נמענים)");
  }
  if (!subject || !body) {
    throw new Error("חסרים subject ו/או body");
  }

  const recipients = to.map((label) => {
    const address = labelToAddress(label);
    if (!address) {
      throw new Error(`נמען לא מורשה: "${label}" - הערכים המותרים הם "me" ו/או "shani" בלבד`);
    }
    return address;
  });

  const fullSubject = `${subject.trim()} - ${SUBJECT_SUFFIX}`;

  await getTransporter().sendMail({
    from: config.myEmail,
    to: recipients.join(", "),
    subject: fullSubject,
    text: body,
  });

  logger.info(`נשלח מייל אל ${recipients.join(", ")} (נושא: ${fullSubject})`);
  return { recipients, subject: fullSubject };
}
