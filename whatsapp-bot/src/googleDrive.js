import { GoogleAuth } from "google-auth-library";
import AdmZip from "adm-zip";
import mammoth from "mammoth";
import { config } from "./config.js";
import { SUPPORTED_IMAGE_MIME_TYPES, DOCX_MIME_TYPE, PPTX_MIME_TYPE, isMarkdownFile } from "./mediaContent.js";

const XML_ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };

/**
 * חילוץ טקסט מינימלי מקובץ PowerPoint (pptx): הקובץ הוא ארכיון zip, וכל שקופית
 * היא קובץ XML נפרד (ppt/slides/slideN.xml) עם ריצות טקסט בתוך תגיות <a:t>.
 * לא נעזרים בספרייה ייעודית (כמו mammoth ל-Word) כדי לא לגרור תלויות כבדות
 * (ספריות פענוח pptx מלאות נוטות לגרור גם מנועי OCR/רינדור PDF שאין בהם צורך כאן).
 */
function extractPptxText(buffer) {
  const zip = new AdmZip(buffer);
  const slideEntries = zip
    .getEntries()
    .filter((e) => /^ppt\/slides\/slide\d+\.xml$/.test(e.entryName))
    .sort((a, b) => {
      const numOf = (name) => Number(name.match(/slide(\d+)\.xml$/)[1]);
      return numOf(a.entryName) - numOf(b.entryName);
    });

  const decodeEntities = (text) =>
    text.replace(/&(amp|lt|gt|quot|apos);/g, (_, ent) => XML_ENTITIES[ent]);

  return slideEntries
    .map((entry, i) => {
      const xml = entry.getData().toString("utf8");
      const runs = [...xml.matchAll(/<a:t>([^<]*)<\/a:t>/g)].map((m) => decodeEntities(m[1]));
      return `[שקופית ${i + 1}]\n${runs.join(" ")}`;
    })
    .join("\n\n");
}

// גישה לגוגל דרייב דרך Service Account: רואה/יכולה לערוך רק קבצים/תיקיות ששותפו
// בפועל עם כתובת המייל של ה-Service Account (לא כל הדרייב האישי של אף אחד) - זו
// גבולת ההרשאה הטבעית והבטוחה של המנגנון, בלי צורך ב-OAuth consent מול המשתמש.
// היקף (scope) מלא של drive (לא drive.readonly) כדי לאפשר גם כתיבה - אבל כתיבה בפועל
// עדיין דורשת ששיתפתם את התיקייה עם הרשאת Editor (לא Viewer), אחרת גוגל תדחה את הבקשה
// בלי קשר ל-scope של הטוקן.
const DRIVE_API = "https://www.googleapis.com/drive/v3";
const DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3/files";
const SCOPES = ["https://www.googleapis.com/auth/drive"];

// יצוא Google Docs/Slides/Sheets ל"טקסט רגיל" - פשוט ואמין יותר מהמרה ל-PDF,
// ומספיק לצורך ניתוח תוכן (לא נדרשת שמירה על עיצוב חזותי).
const GOOGLE_NATIVE_EXPORT_MIME_TYPE = {
  "application/vnd.google-apps.document": "text/plain",
  "application/vnd.google-apps.presentation": "text/plain",
  "application/vnd.google-apps.spreadsheet": "text/csv",
};

let authClientPromise = null;
function getAuthClient() {
  if (!config.googleServiceAccountJson) {
    throw new Error(
      "גישה לגוגל דרייב לא מוגדרת (חסר GOOGLE_SERVICE_ACCOUNT_JSON במשתני הסביבה)."
    );
  }
  if (!authClientPromise) {
    let credentials;
    try {
      credentials = JSON.parse(config.googleServiceAccountJson);
    } catch (err) {
      throw new Error(`GOOGLE_SERVICE_ACCOUNT_JSON אינו JSON תקין: ${err.message}`);
    }
    authClientPromise = new GoogleAuth({ credentials, scopes: SCOPES }).getClient();
  }
  return authClientPromise;
}

function escapeDriveQueryValue(value) {
  return value.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
}

async function driveRequest(path, { params, responseType } = {}) {
  const client = await getAuthClient();
  const url = new URL(`${DRIVE_API}${path}`);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }
  const res = await client.request({ url: url.toString(), responseType });
  return res.data;
}

/** מחפש קבצים (לפי שם ותוכן) בין הקבצים ששותפו עם ה-Service Account. */
export async function searchDriveFiles(query) {
  const q = `fullText contains '${escapeDriveQueryValue(query)}' and trashed = false`;
  const data = await driveRequest("/files", {
    params: {
      q,
      fields: "files(id,name,mimeType,modifiedTime)",
      pageSize: 15,
      includeItemsFromAllDrives: true,
      supportsAllDrives: true,
      corpora: "allDrives",
    },
  });
  return data.files || [];
}

/**
 * קורא קובץ בודד מגוגל דרייב לפי fileId, ומחזיר אובייקט מדיה תואם ל-mediaToContentBlocks
 * (kind: "document"/"image"/"docx-text"/"pptx-text"), בתוספת שם הקובץ.
 */
export async function readDriveFile(fileId) {
  const meta = await driveRequest(`/files/${fileId}`, {
    params: { fields: "id,name,mimeType", supportsAllDrives: true },
  });
  const { name, mimeType } = meta;

  const exportMimeType = GOOGLE_NATIVE_EXPORT_MIME_TYPE[mimeType];
  if (exportMimeType) {
    const text = await driveRequest(`/files/${fileId}/export`, {
      params: { mimeType: exportMimeType },
      responseType: "text",
    });
    return { name, mimeType, media: { kind: "docx-text", text } };
  }

  const raw = await driveRequest(`/files/${fileId}`, {
    params: { alt: "media", supportsAllDrives: true },
    responseType: "arraybuffer",
  });
  const buffer = Buffer.from(raw);

  if (mimeType === "application/pdf") {
    return { name, mimeType, media: { kind: "document", mimeType, base64: buffer.toString("base64") } };
  }
  if (SUPPORTED_IMAGE_MIME_TYPES.includes(mimeType)) {
    return { name, mimeType, media: { kind: "image", mimeType, base64: buffer.toString("base64") } };
  }
  if (mimeType === DOCX_MIME_TYPE) {
    const { value: text } = await mammoth.extractRawText({ buffer });
    return { name, mimeType, media: { kind: "docx-text", text } };
  }
  if (mimeType === PPTX_MIME_TYPE) {
    return { name, mimeType, media: { kind: "pptx-text", text: extractPptxText(buffer) } };
  }
  if (isMarkdownFile({ mimeType, fileName: name })) {
    return { name, mimeType, media: { kind: "markdown-text", text: buffer.toString("utf8") } };
  }

  throw new Error(`סוג קובץ לא נתמך לקריאה: ${mimeType} (נתמכים: PDF, Word, PowerPoint, Markdown, תמונה, וקבצי Google Docs/Slides/Sheets)`);
}

/** יוצר קובץ Markdown חדש בתיקיית היעד (GOOGLE_DRIVE_FOLDER_ID), ומחזיר {id, name, webViewLink}. */
export async function writeDriveFile(fileName, content) {
  if (!config.googleDriveFolderId) {
    throw new Error("כתיבה לגוגל דרייב לא מוגדרת (חסר GOOGLE_DRIVE_FOLDER_ID במשתני הסביבה).");
  }
  const client = await getAuthClient();
  const metadata = { name: fileName, parents: [config.googleDriveFolderId], mimeType: "text/markdown" };

  const res = await client.request({
    url: `${DRIVE_UPLOAD_API}?uploadType=multipart&supportsAllDrives=true&fields=id,name,webViewLink`,
    method: "POST",
    multipart: [
      { headers: { "Content-Type": "application/json; charset=UTF-8" }, content: JSON.stringify(metadata) },
      { headers: { "Content-Type": "text/markdown; charset=UTF-8" }, content },
    ],
  });
  return res.data;
}
