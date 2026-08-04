"""OCR עבור מסמכי PDF סרוקים (בלי word נלווה) שחילוץ הטקסט הרגיל (pdfplumber/
pypdf) נכשל עליהם לגמרי (has_document=0, text_length=0) - נבדק ואומת (ראו
דיון עם המשתמש) שאלה סריקות אמיתיות (image XObject, בלי משאבי פונט כלל),
לא קובץ פגום/timeout - ז"א OCR הוא הפתרון הנכון, לא באג בקוד הקיים.

מנוע: Tesseract 5 (heb.traineddata) - הותקן ע"י המשתמש עם הרשאות אדמין
(choco install tesseract), כי לא ניתן להתקין binary חיצוני מתוך sandbox
ההרצה הזו. נבדק ידנית מול 3 מסמכים אמיתיים: טקסט ה-body (הגוף המהותי של
פסק הדין) מתחלץ כמעט-מושלם; רק אזורי חותמות/שוליים מכניסים רעש - איכות
מספיק טובה לחיפוש טקסט מלא.

לכל מסמך שה-OCR הצליח עליו (טקסט לא ריק):
1. מעדכן has_document=1, text_length, ומריץ extract_metadata() על הטקסט
   החדש - **לא רק judge/decision_date**: נמצא בפועל (בבדיקה מדגמית של
   המשתמש!) ש-76.8% מהמועמדים הגיעו עם case_number ריק לגמרי (ו-29.6%
   עם court ריק) - כי הקבצים האלה נפלו בין הכיסאות של ה-CSV ההיסטורי
   (קובץ שלא כיסה את כל המסמכים בפועל) ועברו דרך הנתיב ה'ללא-CSV' של
   ingest.py, שמנסה לחלץ מטא-דאטה מגוף המסמך - וכשאין טקסט (has_document=0)
   כל השדות יוצאים ריקים. עכשיו, כשיש טקסט אמיתי, extract_metadata()
   יכול למלא את זה בפעם הראשונה. **לא דורסים שדה שכבר יש בו ערך אמיתי**
   (מה-CSV, אמין יותר מ-OCR) - רק ממלאים מה שהיה ריק.
2. מעלה את הטקסט המלא ל-R2 (fulltext/{id}.txt.gz) - דורס את הריק שהיה שם.
3. מעדכן את verdicts_fts (contentless - צריך delete+insert, לא UPDATE רגיל).
4. דוחף את אותו עדכון ל-Turso (turso_sync.sync() הרגיל דוחף רק רשומות
   *חדשות* לפי id - כאן מעדכנים רשומות *קיימות*, לכן צריך UPDATE ישיר
   דרך Hrana/HTTP, לא את sync()).

resumable: לוג התקדמות (data/ocr_progress.csv) - מדלג על id שכבר טופל.

הרצה:  python _ocr_scanned_pdfs.py [workers] [limit]
  workers: כמה thread-ים במקביל. **חשוב: נבדק בפועל ש-ProcessPoolExecutor
           (תהליכים נפרדים, לא threads) גורם ל-crash מ-חוסר זיכרון על
           המחשב הזה** (רק ~2.3GB פנויים מתוך 16.5GB - שאר הזיכרון תפוס
           ע"י Chrome/OneDrive/תהליכים אחרים) - כל תהליך פייתון נפרד
           (fitz+PIL+pytesseract) צורך זיכרון בסיס משמעותי, וכפול-12
           זה יותר מדי. Thread-ים חולקים תהליך אחד (זול בזיכרון) - כל
           thread רק קורא ל-tesseract.exe כתהליך-משנה קל. נבדק: רינדור
           PyMuPDF לא משחרר GIL (thread-ים לא מאיצים את זה), אבל קריאות
           tesseract.exe עצמן כן מקביליות אמיתי ברמת המערכת - וזה השכבה
           הדומיננטית בזמן הריצה, אז threads עדיין נותנים תאוצה אמיתית.
           ברירת מחדל: 10.
  limit:   מספר מסמכים מקסימלי (לבדיקת פיילוט; בלי ארגומנט = כל המועמדים)
"""
from __future__ import annotations

import csv
import io
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fitz
import pytesseract
from PIL import Image

sys.path.insert(0, ".")
from zot import config, storage, turso_sync  # noqa: E402
from zot.extract import extract_metadata  # noqa: E402

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

ROOT = Path(__file__).resolve().parent
PROGRESS_CSV = config.DATA_DIR / "ocr_progress.csv"
DPI = 200
_MIN_TEXT_LEN = 30  # מתחת לזה - נחשב 'OCR נכשל', לא מעדכנים has_document


def local_path(relpath: str) -> Path:
    if relpath.startswith("nethamishpat_recovery/"):
        return ROOT / "data" / "nethamishpat" / "recovery_full" / relpath[len("nethamishpat_recovery/"):]
    if relpath.startswith("nethamishpat/"):
        return ROOT / "documents_nethamishpat" / relpath[len("nethamishpat/"):]
    if relpath.startswith("supreme/"):
        return ROOT / "documents_supreme" / relpath[len("supreme/"):]
    if relpath.startswith("ngcs_2012_2019/"):
        return ROOT / "documents_ngcs_2012_2019" / relpath[len("ngcs_2012_2019/"):]
    return config.DOCS_DIR / relpath


def ocr_doc(doc) -> str:
    # --oem 1 (LSTM-only, skip the redundant legacy engine) + raw pixel samples
    # instead of a PNG encode/decode round-trip - benchmarked on 5 real scanned
    # docs from this corpus: 32% faster (6.83s/doc vs 10.04s/doc), essentially
    # identical extracted text (5166 vs 5180 chars) and lower peak memory per
    # page (no compressed-PNG buffer). oem3 (the tesseract default, used before
    # this change) redundantly runs the legacy engine alongside LSTM and is
    # strictly slower for this workload with no measured quality gain.
    parts = []
    for page in doc:
        pix = page.get_pixmap(dpi=DPI)
        mode = "RGB" if pix.n < 4 else "RGBA"
        img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        parts.append(pytesseract.image_to_string(img, lang="heb", config="--oem 1"))
    return "\n".join(parts)


def _process(row: dict):
    """רץ ב-thread נפרד (ThreadPoolExecutor - ראו למה לא ProcessPoolExecutor
    למעלה). מחזיר רק נתונים - שום עדכון DB/R2/Turso כאן (זה קורה ב-thread
    הראשי, שם מרוכזים כל ה-side effects, למניעת race conditions).

    אם העותק המקומי כבר נמחק (מרוץ-תנאים מול ה-cleanup של סקריפט ה-ingest,
    שמעלה ל-R2 ואז מוחק מקומית אחרי גיל מינימלי - ראו _ngcs_2012_2019_
    ingest_and_cleanup.py) - נופלים חזרה לשליפה מ-R2 (storage.fetch_document,
    אותו key בדיוק כמו file_relpath_pdf, ראו zot/ingest.py:docs_prefix)
    לפני שמוותרים. קריטי: status='missing' הוא סופי-לצמיתות (_load_done
    מדלג עליו גם בהרצות עתידיות) - בלי הנפילה-חזרה הזו, כל מסמך שנמחק
    מקומית *לפני* שה-OCR הגיע אליו היה אובד לצמיתות מנקודת המבט של
    הסקריפט הזה (הקובץ עדיין קיים ב-R2 לתמיד, אבל אף אחד לא היה שולף
    אותו משם שוב)."""
    path = local_path(row["file_relpath_pdf"])
    try:
        if path.exists():
            doc = fitz.open(str(path))
        else:
            data = storage.fetch_document(row["file_relpath_pdf"])
            if data is None:
                return row["id"], None, "missing"
            doc = fitz.open(stream=data, filetype="pdf")
        text = ocr_doc(doc)
    except Exception as e:  # noqa: BLE001
        print(f"  שגיאת OCR עבור id={row['id']} ({path}): {type(e).__name__}: {e}", flush=True)
        return row["id"], None, "failed"
    if len(text.strip()) < _MIN_TEXT_LEN:
        return row["id"], None, "failed"
    return row["id"], text, "ok"


def _load_done() -> set[int]:
    done = set()
    if PROGRESS_CSV.exists():
        with open(PROGRESS_CSV, encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[1] in ("ok", "failed", "missing"):
                    done.add(int(row[0]))
    return done


def _push_turso_update(rows: list[dict]) -> None:
    """rows: [{id, old_parties, old_judge, old_court, old_case_number,
    old_matter, old_decision_type, new_parties, new_judge, new_court,
    new_case_number, new_case_type, new_decision_type, new_decision_date,
    text_length, full_text}] - מעדכן רשומות *קיימות* ב-Turso (לא sync() -
    זה רק לחדשות). matter תמיד נשאר כמו שהיה (לא נגזר מ-extract_metadata)."""
    if not config.TURSO_DATABASE_URL or not rows:
        return
    statements: list[tuple[str, list]] = []
    for r in rows:
        # מחיקת הערך הריק הישן מ-verdicts_fts (contentless - לא ניתן UPDATE ישיר)
        statements.append((
            "INSERT INTO verdicts_fts(verdicts_fts, rowid, parties, judge, court, "
            "case_number, matter, decision_type, full_text) VALUES ('delete',?,?,?,?,?,?,?,?)",
            [r["id"], r["old_parties"], r["old_judge"], r["old_court"], r["old_case_number"],
             r["old_matter"], r["old_decision_type"], ""],
        ))
        statements.append((
            "INSERT INTO verdicts_fts(rowid, parties, judge, court, case_number, "
            "matter, decision_type, full_text) VALUES (?,?,?,?,?,?,?,?)",
            [r["id"], r["new_parties"], r["new_judge"], r["new_court"], r["new_case_number"],
             r["old_matter"], r["new_decision_type"], r["full_text"]],
        ))
        statements.append((
            "UPDATE verdicts SET has_document=1, text_length=?, judge=?, decision_date=?, "
            "parties=?, court=?, case_number=?, case_type=?, decision_type=? WHERE id=?",
            [r["text_length"], r["new_judge"], r["new_decision_date"], r["new_parties"],
             r["new_court"], r["new_case_number"], r["new_case_type"], r["new_decision_type"], r["id"]],
        ))
        # מחזיק את distinct_values מעודכן (ראו zot/search.py: _distinct_values) -
        # השלמת מטא-דאטה כאן עלולה להביא ערך court/case_type חדש לגמרי.
        for field, val in (("court", r["new_court"]), ("case_type", r["new_case_type"])):
            if val:
                statements.append((
                    "INSERT OR IGNORE INTO distinct_values(field, value) VALUES (?,?)",
                    [field, val],
                ))
    turso_sync._run_batch(statements)


def main() -> int:
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None

    conn = sqlite3.connect(str(config.DB_PATH), timeout=30)
    done_ids = _load_done()
    print(f"{len(done_ids)} מסמכים כבר טופלו (resumable) - מדלג עליהם.", flush=True)

    q = """SELECT id, file_relpath_pdf, case_number, parties, court, matter,
                  case_type, decision_type, judge, decision_date
           FROM verdicts WHERE has_document=0 AND (file_relpath_docx='' OR file_relpath_docx IS NULL)
                 AND file_relpath_pdf != ''"""
    rows = conn.execute(q).fetchall()
    cols = ["id", "file_relpath_pdf", "case_number", "parties", "court", "matter",
            "case_type", "decision_type", "judge", "decision_date"]
    candidates = [dict(zip(cols, r)) for r in rows if r[0] not in done_ids]
    if limit:
        candidates = candidates[:limit]
    print(f"{len(rows)} מועמדים סה\"כ, {len(candidates)} לעיבוד בהרצה זו.", flush=True)

    progress_f = open(PROGRESS_CSV, "a", newline="", encoding="utf-8-sig")
    progress_w = csv.writer(progress_f)

    t0 = time.time()
    ok = failed = missing = 0
    pending_turso: list[dict] = []
    pending_uploads: list[tuple[int, str]] = []

    def _flush():
        nonlocal pending_turso, pending_uploads
        # commit local FIRST, before the network calls below - otherwise the
        # local write lock stays held for the whole R2+Turso round-trip
        # (can run well past any reasonable busy_timeout) and any other
        # process writing to index.db concurrently (e.g. fetch_daily.py's
        # ingest.build()) hard-fails with "database is locked".
        conn.commit()
        if pending_uploads:
            storage.upload_fulltexts(pending_uploads, verbose=False)
            pending_uploads = []
        if pending_turso:
            _push_turso_update(pending_turso)
            pending_turso = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process, row): row for row in candidates}
        n = 0
        for fut in as_completed(futures):
            row = futures[fut]
            id_, text, status = fut.result()
            n += 1
            if status == "ok":
                meta = extract_metadata(text)
                case_number = row["case_number"] or meta["case_number"]
                court = row["court"] or meta["court"]
                parties = row["parties"] or meta["parties"]
                case_type = row["case_type"] or meta["case_type"]
                decision_type = row["decision_type"] or meta["decision_type"]
                judge = row["judge"] or meta["judge"]
                decision_date = row["decision_date"] or meta["decision_date"]
                conn.execute(
                    "UPDATE verdicts SET has_document=1, text_length=?, judge=?, decision_date=?, "
                    "parties=?, court=?, case_number=?, case_type=?, decision_type=? WHERE id=?",
                    (len(text), judge, decision_date, parties, court, case_number,
                     case_type, decision_type, id_),
                )
                conn.execute(
                    "INSERT INTO verdicts_fts(verdicts_fts, rowid, parties, judge, court, "
                    "case_number, matter, decision_type, full_text) VALUES ('delete',?,?,?,?,?,?,?,?)",
                    (id_, row["parties"], row["judge"], row["court"], row["case_number"],
                     row["matter"], row["decision_type"], ""),
                )
                conn.execute(
                    "INSERT INTO verdicts_fts(rowid, parties, judge, court, case_number, "
                    "matter, decision_type, full_text) VALUES (?,?,?,?,?,?,?,?)",
                    (id_, parties, judge, court, case_number,
                     row["matter"], decision_type, text),
                )
                pending_uploads.append((id_, text))
                pending_turso.append({
                    "id": id_,
                    "old_case_number": row["case_number"], "old_parties": row["parties"],
                    "old_court": row["court"], "old_matter": row["matter"],
                    "old_decision_type": row["decision_type"], "old_judge": row["judge"],
                    "new_case_number": case_number, "new_parties": parties,
                    "new_court": court, "new_case_type": case_type,
                    "new_decision_type": decision_type, "new_judge": judge,
                    "new_decision_date": decision_date, "text_length": len(text),
                    "full_text": text,
                })
                ok += 1
            elif status == "missing":
                missing += 1
            else:
                failed += 1
            progress_w.writerow([id_, status])
            if n % 200 == 0:
                progress_f.flush()
                _flush()
                elapsed = time.time() - t0
                rate = n / elapsed * 60
                eta_h = (len(candidates) - n) / max(rate, 0.01) / 60
                print(f"[{n}/{len(candidates)}] ok={ok} failed={failed} missing={missing} "
                      f"| {rate:.0f}/min | ETA {eta_h:.1f}h", flush=True)

    _flush()
    progress_f.close()
    conn.close()
    print(f"\nDONE. ok={ok} failed={failed} missing={missing} "
          f"total_time={(time.time()-t0)/60:.1f}min", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
