#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""שולח מייל סיכום יומי (18:30) עם שני חלקים:
  1. ההורדה היומית (fetch_daily.py + run_daily.bat): הצליחה? כמה החלטות
     חדשות ירדו, הועלו ל-R2, ונכנסו לאינדקס.
  2. בוט החיסיון (confidentiality_bot.py): כמה מיילים נבדקו היום וכמה
     הליכים/החלטות הוסרו.

מריצים פעם ביום ב-18:30 — ראו המשימה המתוזמנת GiluyNaot-DailySummary.

הרצה:  python daily_summary_email.py
"""
from __future__ import annotations

import re
import smtplib
import sys
from datetime import date
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from zot import config  # noqa: E402

DAILY_LOG = ROOT / "daily_log.txt"
BOT_LOG = ROOT / "confidentiality_bot_log.txt"

_SECTION_RE = re.compile(r"^==== .+ ====\s*$")
_DOWNLOAD_SUMMARY_RE = re.compile(
    r"סיכום הורדה: (\d+) קבצים חדשים, (\d+) כבר קיימים, (\d+) שגיאות"
)
_R2_UPLOAD_RE = re.compile(
    r"העלאה ל-R2: (\d+) קבצים חדשים, (\d+) כבר הועלו, (\d+) שגיאות"
)
_INDEX_SKIPPED_RE = re.compile(r"תהליך בניית אינדקס אחר כבר רץ ברקע")
_INDEX_BUILT_RE = re.compile(r"(נוספו|נבנה אינדקס:) (\d+) רשומות חדשות")
_INDEX_UPLOAD_OK_RE = re.compile(r"האינדקס \(([\d.]+)MB\) הועלה ל-R2")
_INDEX_UPLOAD_FAIL_RE = re.compile(r"העלאת האינדקס נכשלה סופית")

_BOT_CHECKED_RE = re.compile(r"נבדקו (\d+) מיילים חדשים, (\d+) אזכורי תיק")
_BOT_SUMMARY_RE = re.compile(
    r"סיכום: (\d+) תיקים נמצאו במאגר, (\d+) שורות נמחקו, (\d+) קבצים נמחקו"
)


def _last_section(text: str) -> str:
    """מחזיר את הקטע האחרון בלוג (מ-'====' האחרון ועד סוף הקובץ)."""
    lines = text.splitlines()
    last_start = 0
    for i, line in enumerate(lines):
        if _SECTION_RE.match(line):
            last_start = i
    return "\n".join(lines[last_start:])


def summarize_daily_download() -> str:
    if not DAILY_LOG.exists():
        return "לא נמצא daily_log.txt — ההורדה היומית כנראה לא רצה היום."

    # daily_log.txt נכתב ע"י run_daily.bat דרך הפניית קונסולת Windows (>>),
    # שמשתמשת ב-cp1255 (עברית) ולא ב-UTF-8 — בניגוד לרוב קבצי הפרויקט.
    text = DAILY_LOG.read_text(encoding="cp1255", errors="replace")
    section = _last_section(text)

    dl_m = _DOWNLOAD_SUMMARY_RE.search(section)
    r2_m = _R2_UPLOAD_RE.search(section)
    idx_ok_m = _INDEX_UPLOAD_OK_RE.search(section)
    idx_fail = bool(_INDEX_UPLOAD_FAIL_RE.search(section))

    if not dl_m:
        return "לא נמצאה ריצת הורדה תקינה בלוג של היום (ייתכן שנכשלה לפני שהגיעה לסיכום)."

    new_files, existing, dl_errors = (int(x) for x in dl_m.groups())
    lines = [
        f"החלטות חדשות שירדו היום: {new_files} "
        f"(מתוך {new_files + existing:,} קבצים שנבדקו בטווח הימים שנסרק, "
        f"{existing:,} כבר היו קיימים מהורדות קודמות)."
    ]
    if dl_errors:
        lines.append(f"אזהרה: {dl_errors} שגיאות בהורדה.")

    if r2_m:
        r2_new, r2_existing, r2_errors = (int(x) for x in r2_m.groups())
        lines.append(f"הועלו ל-R2: {r2_new} קבצים חדשים.")
        if r2_errors:
            lines.append(f"אזהרה: {r2_errors} שגיאות בהעלאה ל-R2.")
    else:
        lines.append("אזהרה: לא נמצא סיכום העלאת קבצים ל-R2.")

    if _INDEX_SKIPPED_RE.search(section):
        lines.append("בניית האינדקס דולגה (תהליך אינדוקס אחר כבר רץ ברקע) — ייתפס בהרצה שלו.")
    else:
        built_m = _INDEX_BUILT_RE.search(section)
        if built_m:
            lines.append(f"נוספו לאינדקס: {built_m.group(2)} רשומות חדשות.")

    if idx_ok_m:
        lines.append(f"קובץ האינדקס ({idx_ok_m.group(1)}MB) הועלה ל-R2 בהצלחה — האתר יתעדכן תוך כשעה.")
    elif idx_fail:
        lines.append("אזהרה: העלאת קובץ האינדקס ל-R2 נכשלה סופית — האתר לא מעודכן!")
    else:
        lines.append("אזהרה: לא נמצאה הודעת הצלחה/כישלון להעלאת קובץ האינדקס.")

    success = dl_errors == 0 and (not r2_m or r2_m.group(3) == "0") and not idx_fail
    status = "תקין: ההורדה היומית הצליחה במלואה." if success else "אזהרה: ההורדה היומית לא הצליחה במלואה — ראו פירוט למטה."
    return status + "\n" + "\n".join(lines)


def summarize_confidentiality_bot() -> str:
    if not BOT_LOG.exists():
        return "הבוט עדיין לא רץ (אין קובץ לוג)."

    today = date.today().isoformat()
    checked_total = mentions_total = 0
    cases_total = rows_total = files_total = 0
    ran_today = False

    for line in BOT_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith(f"[{today}"):
            continue
        ran_today = True
        m = _BOT_CHECKED_RE.search(line)
        if m:
            checked_total += int(m.group(1))
            mentions_total += int(m.group(2))
        m = _BOT_SUMMARY_RE.search(line)
        if m:
            cases_total += int(m.group(1))
            rows_total += int(m.group(2))
            files_total += int(m.group(3))

    if not ran_today:
        return "הבוט לא רץ היום (או שאין עדיין ריצות מתועדות)."

    return (
        f"מיילים חדשים שנבדקו היום: {checked_total}.\n"
        f"תיקים שנמצאו במאגר והוסרו: {cases_total} "
        f"({rows_total} שורות/החלטות, {files_total} קבצים)."
    )


def send_email(body: str) -> None:
    if not config.GMAIL_USER or not config.GMAIL_APP_PASSWORD:
        print("GMAIL_USER/GMAIL_APP_PASSWORD לא מוגדרים — לא ניתן לשלוח מייל.")
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"גילוי נאות — סיכום יומי {date.today().isoformat()}"
    msg["From"] = config.GMAIL_USER
    msg["To"] = config.GMAIL_USER

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
        server.send_message(msg)


def main() -> int:
    body = (
        "=== הורדה יומית ===\n" + summarize_daily_download() + "\n\n"
        "=== בוט חיסיון ===\n" + summarize_confidentiality_bot() + "\n"
    )
    print(body)
    send_email(body)
    print("מייל סיכום נשלח.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
