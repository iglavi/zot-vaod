import fs from "node:fs";
import path from "node:path";

/**
 * אחסון פשוט מבוסס קובץ JSON, עם כתיבה אטומית (כתיבה לקובץ זמני ואז החלפה)
 * כדי לא להשאיר קובץ פגום אם התהליך נופל באמצע כתיבה.
 */
export class JsonStore {
  constructor(filePath, defaultValue) {
    this.filePath = filePath;
    this.data = this.#load(defaultValue);
  }

  #load(defaultValue) {
    try {
      const raw = fs.readFileSync(this.filePath, "utf8");
      return JSON.parse(raw);
    } catch {
      return structuredClone(defaultValue);
    }
  }

  get(key, fallback) {
    return Object.prototype.hasOwnProperty.call(this.data, key) ? this.data[key] : fallback;
  }

  set(key, value) {
    this.data[key] = value;
    this.#persist();
  }

  delete(key) {
    delete this.data[key];
    this.#persist();
  }

  all() {
    return this.data;
  }

  #persist() {
    const dir = path.dirname(this.filePath);
    fs.mkdirSync(dir, { recursive: true });
    const tmpPath = `${this.filePath}.tmp`;
    fs.writeFileSync(tmpPath, JSON.stringify(this.data, null, 2), "utf8");
    fs.renameSync(tmpPath, this.filePath);
  }
}
