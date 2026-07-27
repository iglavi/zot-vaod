// סוגי קבצים שהסוכן יכול "לראות" בפועל (תמונות ו-PDF מצורפים כמו שהם; Word/PowerPoint
// מחולצים לטקסט - Claude לא קורא קובצי docx/pptx גולמיים). משותף בין קבצים מצורפים
// בוואטסאפ (whatsapp.js) לבין קבצים שנקראים מגוגל דרייב (googleDrive.js).
export const SUPPORTED_IMAGE_MIME_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
export const DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
export const PPTX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation";

/**
 * ממיר אובייקט מדיה (כפי שמורד ב-whatsapp.js) לרשימת בלוקי תוכן שאפשר לצרף
 * להודעת user.message. משותף לכל הסוכנים (ליצי, חבר) כדי לא לשכפל את הלוגיקה הזו.
 *
 * - image/document (PDF): נשלחים כמו שהם ב-base64, כדי שהסוכן "יראה" אותם ממש.
 * - docx-text/pptx-text: Word/PowerPoint אינם נתמכים כקובץ מצורף ישיר על ידי Claude,
 *   אז התוכן כבר חולץ לטקסט רגיל (בעזרת mammoth/officeparser) ומגיע לכאן כטקסט מוכן.
 */
export function mediaToContentBlocks(media) {
  if (!media) return [];

  if (media.kind === "image" || media.kind === "document") {
    return [
      {
        type: media.kind,
        source: { type: "base64", media_type: media.mimeType, data: media.base64 },
      },
    ];
  }

  if (media.kind === "docx-text") {
    return [{ type: "text", text: `[תוכן קובץ Word מצורף]:\n${media.text}` }];
  }

  if (media.kind === "pptx-text") {
    return [{ type: "text", text: `[תוכן קובץ PowerPoint מצורף]:\n${media.text}` }];
  }

  return [];
}
