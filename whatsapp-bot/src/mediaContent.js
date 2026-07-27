/**
 * ממיר אובייקט מדיה (כפי שמורד ב-whatsapp.js) לרשימת בלוקי תוכן שאפשר לצרף
 * להודעת user.message. משותף לכל הסוכנים (ליצי, חבר) כדי לא לשכפל את הלוגיקה הזו.
 *
 * - image/document (PDF): נשלחים כמו שהם ב-base64, כדי שהסוכן "יראה" אותם ממש.
 * - docx-text: Word אינו נתמך כקובץ מצורף ישיר על ידי Claude, אז התוכן כבר חולץ
 *   לטקסט רגיל (ב-whatsapp.js, בעזרת mammoth) ומגיע לכאן כטקסט מוכן.
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

  return [];
}
