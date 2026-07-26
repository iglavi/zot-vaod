import { config } from "./config.js";

/**
 * זיכרון-רקע זמני (בזיכרון התהליך בלבד, לא נשמר לדיסק ולא נשלח ל-API באופן ישיר) —
 * שומר את ה-N ההודעות האחרונות בכל קבוצה, כדי לתת לסוכן הקשר כשמבקשים ממנו סיכום.
 * נמחק בכל הפעלה מחדש של הבוט - וזה בסדר, זו רק "זיכרון קצר טווח".
 */
class MessageBuffer {
  constructor(maxPerChat) {
    this.maxPerChat = maxPerChat;
    /** @type {Map<string, Array<{ sender: string, text: string, timestamp: number }>>} */
    this.byChat = new Map();
  }

  add(chatId, entry) {
    if (!this.byChat.has(chatId)) this.byChat.set(chatId, []);
    const list = this.byChat.get(chatId);
    list.push(entry);
    while (list.length > this.maxPerChat) list.shift();
  }

  get(chatId) {
    return this.byChat.get(chatId) || [];
  }

  /** מפרמט את ההודעות האחרונות כתמליל קריא לשליחה כהקשר לסוכן. */
  formatTranscript(chatId, { limit = this.maxPerChat } = {}) {
    const list = this.get(chatId).slice(-limit);
    if (list.length === 0) return "(אין הודעות רקע קודמות בזיכרון)";
    return list
      .map((m) => `${m.sender}: ${m.text}`)
      .join("\n");
  }
}

export const messageBuffer = new MessageBuffer(config.messageBufferSize);
