#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""בוט חיסיון: קורא מיילים מ-DecisionsPublishing@court.gov.il בנושא "עדכון
אודות שינוי רמת החסיון של תיק", ומסיר מהמאגר (מסד + קבצים מקומיים + R2)
כל הליך/החלטה שצוינו בהם.

כלל ברירת המחדל: הסרת ההליך כולו. חריג: אם המייל מציין "החלטה מיום
DD.MM.YYYY" ספציפית — מוסרת רק אותה החלטה (לפי decision_date), לא כל
ההליך.

מריצים כל שעתיים, 06:00-18:00 בלבד (שעות שבהן בפועל מגיעים מיילים כאלה,
לפי בדיקה על 199 מיילים היסטוריים) — ראו את המשימה המתוזמנת
GiluyNaot-ConfidentialityBot. הרצה מחוץ לשעות האלה לא עושה נזק (פשוט
לא ימצא מיילים חדשים), אבל אין טעם להריץ בלילה.

הרצה:  python confidentiality_bot.py
מצב תצוגה-בלבד (בלי למחוק בפועל):  python confidentiality_bot.py --dry-run
"""
from __future__ import annotations

import email
import imaplib
import re
import sqlite3
import sys
import time
from datetime import datetime
from email.header import decode_header
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from zot import config, storage  # noqa: E402

SENDER = "DecisionsPublishing@court.gov.il"
SUBJECT = "עדכון אודות שינוי רמת החסיון של תיק"

PROCESSED_IDS_PATH = config.DATA_DIR / "confidentiality_bot_processed.txt"
LOG_PATH = ROOT / "confidentiality_bot_log.txt"

DB_PATH = config.DB_PATH
DOCS_DIR = config.DOCS_DIR
SUPREME_DOCS_DIR = ROOT / "documents_supreme"

CASE_RE = re.compile(r'תיק(?:ים)?\s+')
NUM_RE = re.compile(r'(\d{1,6}-\d{1,3}-\d{2,4})')
TYPE_RE = re.compile(r'^([א-ת"׳\']{1,10})\s*-?\s*')
DATE_SPECIFIC_RE = re.compile(r'(?:החלטה|החלטת|פרוטוקול|תמלול)\s+מיום\s+(\d{1,2})\.(\d{1,2})\.(\d{2,4})')


def _log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                charset = part.get_content_charset() or "utf-8"
                html = part.get_payload(decode=True).decode(charset, errors="replace")
                return re.sub(r"<[^>]+>", " ", html)
        return ""
    charset = msg.get_content_charset() or "utf-8"
    payload = msg.get_payload(decode=True)
    return payload.decode(charset, errors="replace") if payload else ""


def parse_cases(body: str) -> tuple[list[tuple[str, str]], list[str]]:
    """מחזיר (רשימת (סוג-תיק, מספר-תיק), רשימת תאריכי-ISO של החלטות ספציפיות)."""
    cases = []
    for chunk in CASE_RE.split(body)[1:]:
        num_m = NUM_RE.search(chunk[:60])
        if num_m:
            type_m = TYPE_RE.match(chunk)
            ctype = type_m.group(1).strip() if type_m else ""
            cases.append((ctype, num_m.group(1)))
    date_specific = []
    for d, mo, y in DATE_SPECIFIC_RE.findall(body):
        y = y if len(y) == 4 else f"20{y}"
        try:
            date_specific.append(f"{int(y):04d}-{int(mo):02d}-{int(d):02d}")
        except ValueError:
            continue
    return cases, date_specific


def _execute_retry(conn: sqlite3.Connection, query: str, params, retries: int = 8, delay: int = 5):
    for i in range(retries):
        try:
            return conn.execute(query, params)
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and i < retries - 1:
                time.sleep(delay)
                continue
            raise


def relpath_to_disk(rel: str) -> Path:
    if rel.startswith("supreme/"):
        return SUPREME_DOCS_DIR / rel[len("supreme/"):]
    return DOCS_DIR / rel


def delete_rows(conn: sqlite3.Connection, rows: list[tuple], r2_client, r2_bucket) -> tuple[int, int]:
    """rows: (id, case_number, parties, judge, court, matter, decision_type,
    full_text, file_relpath_pdf, file_relpath_docx, decision_date). מחזיר
    (קבצים-שנמחקו, שורות-שנמחקו)."""
    files_deleted = 0
    for row in rows:
        (rid, case_number, parties, judge, court, matter, decision_type,
         full_text, pdf_rel, docx_rel, _decision_date) = row
        for rel in (pdf_rel, docx_rel):
            if not rel:
                continue
            local_path = relpath_to_disk(rel)
            try:
                if local_path.exists():
                    local_path.unlink()
                    files_deleted += 1
            except Exception as e:  # noqa: BLE001
                _log(f"  שגיאה במחיקת קובץ מקומי {local_path}: {e}")
            if r2_client is not None and r2_bucket:
                try:
                    r2_client.delete_object(Bucket=r2_bucket, Key=rel)
                except Exception as e:  # noqa: BLE001
                    _log(f"  שגיאה במחיקת אובייקט R2 {rel}: {e}")
        _execute_retry(
            conn,
            "INSERT INTO verdicts_fts(verdicts_fts, rowid, parties, judge, court, "
            "case_number, matter, decision_type, full_text) VALUES ('delete', ?,?,?,?,?,?,?,?)",
            (rid, parties, judge, court, case_number, matter, decision_type, full_text),
        )
        _execute_retry(conn, "DELETE FROM verdicts WHERE id=?", (rid,))
    return files_deleted, len(rows)


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    if not config.GMAIL_USER or not config.GMAIL_APP_PASSWORD:
        _log("GMAIL_USER/GMAIL_APP_PASSWORD לא מוגדרים ב-.env — עוצר.")
        return 1

    PROCESSED_IDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    processed_ids = set()
    if PROCESSED_IDS_PATH.exists():
        processed_ids = set(PROCESSED_IDS_PATH.read_text(encoding="utf-8").splitlines())

    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
    imap.select("INBOX")

    status, data = imap.search(None, f'(FROM "{SENDER}")')
    if status != "OK":
        _log(f"שגיאה בחיפוש IMAP: {status}")
        imap.logout()
        return 1
    msg_nums = data[0].split()

    new_cases: list[tuple[str, str, list[str], str]] = []  # (ctype, num, date_specific, msg_id)
    newly_checked_ids: list[str] = []
    checked = 0
    for num in msg_nums:
        status, msg_data = imap.fetch(num, "(RFC822)")
        if status != "OK":
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        subject = _decode(msg.get("Subject"))
        if SUBJECT not in subject:
            continue
        msg_id = msg.get("Message-ID", "") or f"<no-id-{num.decode()}>"
        if msg_id in processed_ids:
            continue
        checked += 1
        newly_checked_ids.append(msg_id)
        body = _extract_body(msg)
        cases, date_specific = parse_cases(body)
        for ctype, cnum in cases:
            new_cases.append((ctype, cnum, date_specific, msg_id))

    imap.logout()

    _log(f"נבדקו {checked} מיילים חדשים, {len(new_cases)} אזכורי תיק.")

    if checked == 0:
        return 0

    if not new_cases:
        with PROCESSED_IDS_PATH.open("a", encoding="utf-8") as f:
            for msg_id in newly_checked_ids:
                f.write(msg_id + "\n")
        return 0

    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    r2_client = storage._client()
    r2_bucket = config.R2_BUCKET

    total_rows_deleted = 0
    total_files_deleted = 0
    total_cases_matched = 0

    for ctype, cnum, date_specific, msg_id in new_cases:
        rows = conn.execute(
            "SELECT id, case_number, parties, judge, court, matter, decision_type, "
            "full_text, file_relpath_pdf, file_relpath_docx, decision_date "
            "FROM verdicts WHERE case_number=?",
            (cnum,),
        ).fetchall()
        if not rows:
            continue
        if date_specific:
            rows = [r for r in rows if r[10] in date_specific]
            if not rows:
                continue
        total_cases_matched += 1
        _log(f"תיק {ctype} {cnum}: {len(rows)} שורות תואמות "
             f"({'החלטה ספציפית ' + ','.join(date_specific) if date_specific else 'הליך שלם'}).")
        if not dry_run:
            fdel, rdel = delete_rows(conn, rows, r2_client, r2_bucket)
            total_files_deleted += fdel
            total_rows_deleted += rdel

    if not dry_run:
        for i in range(8):
            try:
                conn.commit()
                break
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and i < 7:
                    time.sleep(5)
                    continue
                raise
    conn.close()

    if not dry_run:
        with PROCESSED_IDS_PATH.open("a", encoding="utf-8") as f:
            for msg_id in newly_checked_ids:
                f.write(msg_id + "\n")

    _log(f"סיכום: {total_cases_matched} תיקים נמצאו במאגר, "
         f"{total_rows_deleted} שורות נמחקו, {total_files_deleted} קבצים נמחקו."
         f"{' (DRY RUN — לא בוצע שינוי בפועל)' if dry_run else ''}")

    if not dry_run and total_rows_deleted > 0:
        result = storage.upload_index()
        _log(f"העלאת אינדקס מעודכן ל-R2: {result}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
