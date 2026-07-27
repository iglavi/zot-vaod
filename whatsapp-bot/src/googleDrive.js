import { GoogleAuth } from "google-auth-library";
import { parseOffice } from "officeparser";
import { config } from "./config.js";
import { SUPPORTED_IMAGE_MIME_TYPES, DOCX_MIME_TYPE, PPTX_MIME_TYPE } from "./mediaContent.js";

// גישת קריאה-בלבד לגוגל דרייב דרך Service Account: רואה רק קבצים/תיקיות ששותפו
// בפועל עם כתובת המייל של ה-Service Account (לא כל הדרייב האישי של אף אחד) - זו
// גבולת ההרשאה הטבעית והבטוחה של המנגנון, בלי צורך ב-OAuth consent מול המשתמש.
const DRIVE_API = "https://www.googleapis.com/drive/v3";
const SCOPES = ["https://www.googleapis.com/auth/drive.readonly"];

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
  if (mimeType === DOCX_MIME_TYPE || mimeType === PPTX_MIME_TYPE) {
    const ast = await parseOffice(buffer);
    const kind = mimeType === PPTX_MIME_TYPE ? "pptx-text" : "docx-text";
    return { name, mimeType, media: { kind, text: ast.toText() } };
  }

  throw new Error(`סוג קובץ לא נתמך לקריאה: ${mimeType} (נתמכים: PDF, Word, PowerPoint, תמונה, וקבצי Google Docs/Slides/Sheets)`);
}
