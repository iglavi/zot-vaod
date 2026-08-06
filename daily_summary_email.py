#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""שולח מייל סיכום יומי (18:30) עם שני חלקים:
  1. ההורדה היומית (fetch_daily.py + run_daily.bat): הצליחה? כמה החלטות
     חדשות ירדו, הועלו ל-R2, ונכנסו לאינדקס. מאז 6/8/2026 בוט ההורדה רץ
     פעמיים ביום (07:00 ו-16:00, ראו GiluyNaot-Daily) - הסיכום כאן מצרף
     את כל ריצות היום (לא רק את האחרונה), כדי שהמייל היחיד ב-18:30 ישקף
     את שתיהן.
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
_SECTION_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
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
# תיקיית-תאריך שהושלמה (fetch_daily.py) — משמש לדווח על "התיקייה החדשה
# של היום ומה היה בה" במקום "X מתוך כל הקבצים שאי-פעם נבדקו בכל התיקיות",
# שגדל ללא הפסק עם גיל הארכיון ולא אומר בפועל כלום על ההורדה של היום.
_FOLDER_DONE_RE = re.compile(r"תיקייה (\d{4}-\d{2}-\d{2}): הושלמה \((\d+) פריטים\)\.")

_BOT_CHECKED_RE = re.compile(r"נבדקו (\d+) מיילים חדשים, (\d+) אזכורי תיק")
_BOT_SUMMARY_RE = re.compile(
    r"סיכום: (\d+) תיקים נמצאו במאגר, (\d+) שורות נמחקו, (\d+) קבצים נמחקו"
)


def _all_sections(text: str) -> list[str]:
    """מפצל את הלוג לכל הקטעים (בין שני '====' עוקבים), לא רק האחרון -
    נדרש מאז שבוט ההורדה רץ פעמיים ביום (07:00 ו-16:00)."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if _SECTION_RE.match(line)]
    if not starts:
        return []
    bounds = starts + [len(lines)]
    return ["\n".join(lines[bounds[i]:bounds[i + 1]]) for i in range(len(starts))]


def _section_is_today(section: str) -> bool:
    """קורא את התאריך מכותרת הקטע (למשל '==== Thu 08/06/2026  16:00:01.23
    ====', בפורמט MM/DD/YYYY - כך ש-%date% של Windows כותב) ומשווה להיום."""
    header = section.splitlines()[0] if section else ""
    m = _SECTION_DATE_RE.search(header)
    if not m:
        return False
    month, day, year = m.groups()
    return f"{year}-{month}-{day}" == date.today().isoformat()


def summarize_daily_download() -> str:
    if not DAILY_LOG.exists():
        return "לא נמצא daily_log.txt — ההורדה היומית כנראה לא רצה היום."

    # daily_log.txt נכתב ע"י run_daily.bat דרך הפניית קונסולת Windows (>>),
    # שמשתמשת ב-cp1255 (עברית) ולא ב-UTF-8 — בניגוד לרוב קבצי הפרויקט.
    text = DAILY_LOG.read_text(encoding="cp1255", errors="replace")
    sections = [s for s in _all_sections(text) if _section_is_today(s)]

    if not sections:
        return "לא נמצאה ריצת הורדה תקינה בלוג של היום (ייתכן שנכשלה לפני שהגיעה לסיכום)."

    lines = [f"מספר ריצות הורדה שזוהו היום: {len(sections)}."]
    new_files_total = dl_errors_total = 0
    r2_new_total = r2_errors_total = 0
    r2_seen = False
    built_total = 0
    idx_skipped_any = False
    last_idx_ok_m = None
    idx_fail_any = False
    all_folder_hits: list[tuple[str, str]] = []
    any_dl_match = False

    for section in sections:
        dl_m = _DOWNLOAD_SUMMARY_RE.search(section)
        r2_m = _R2_UPLOAD_RE.search(section)
        idx_ok_m = _INDEX_UPLOAD_OK_RE.search(section)
        if _INDEX_UPLOAD_FAIL_RE.search(section):
            idx_fail_any = True
        if _INDEX_SKIPPED_RE.search(section):
            idx_skipped_any = True
        built_m = _INDEX_BUILT_RE.search(section)
        if built_m:
            built_total += int(built_m.group(2))
        if idx_ok_m:
            last_idx_ok_m = idx_ok_m  # השורה האחרונה כרונולוגית "מנצחת" - מצב האינדקס הנוכחי
        all_folder_hits.extend(_FOLDER_DONE_RE.findall(section))

        if dl_m:
            any_dl_match = True
            new_files, _existing, dl_errors = (int(x) for x in dl_m.groups())
            new_files_total += new_files
            dl_errors_total += dl_errors
        if r2_m:
            r2_seen = True
            r2_new, _r2_existing, r2_errors = (int(x) for x in r2_m.groups())
            r2_new_total += r2_new
            r2_errors_total += r2_errors

    if not any_dl_match:
        return "לא נמצאה ריצת הורדה תקינה בלוג של היום (ייתכן שנכשלה לפני שהגיעה לסיכום)."

    lines.append(f"החלטות/מסמכים חדשים שירדו היום (סה\"כ כל הריצות, בכל התיקיות שנבדקו): {new_files_total:,}.")

    # תיקיית התאריך האחרון (המספר הגבוה ביותר) שנבדקה היא "התיקייה החדשה
    # של היום" — פרק הזמן שהיא צריכה כדי להתייצב הוא 1-2 ימים (ראו ההערה
    # ב-fetch_daily.py), אז מציגים גם את התיקייה שלפניה כדי לראות אם היא
    # עדיין גדלה או כבר יציבה. dict כדי לקחת את הספירה העדכנית ביותר לכל
    # תיקייה (הריצה השנייה של היום עשויה לראות יותר פריטים מהראשונה).
    if all_folder_hits:
        latest_per_folder: dict[str, str] = {}
        for folder_date, count in all_folder_hits:
            latest_per_folder[folder_date] = count
        folder_hits = sorted(latest_per_folder.items())
        newest_date, newest_count = folder_hits[-1]
        lines.append(f"התיקייה החדשה של היום ({newest_date}): {int(newest_count):,} פריטים.")
        if len(folder_hits) > 1:
            prev_date, prev_count = folder_hits[-2]
            lines.append(f"התיקייה של אתמול ({prev_date}): {int(prev_count):,} פריטים "
                         "(עדיין עשויה לגדול יום-יומיים נוספים).")
    else:
        lines.append("אזהרה: לא נמצאה בלוג תיקיית-תאריך שהושלמה היום.")

    if dl_errors_total:
        lines.append(f"אזהרה: {dl_errors_total} שגיאות בהורדה.")

    if r2_seen:
        lines.append(f"הועלו ל-R2: {r2_new_total} קבצים חדשים.")
        if r2_errors_total:
            lines.append(f"אזהרה: {r2_errors_total} שגיאות בהעלאה ל-R2.")
    else:
        lines.append("אזהרה: לא נמצא סיכום העלאת קבצים ל-R2.")

    if built_total:
        lines.append(f"נוספו לאינדקס: {built_total} רשומות חדשות.")
    elif idx_skipped_any:
        lines.append("בניית האינדקס דולגה בלפחות ריצה אחת (תהליך אינדוקס אחר כבר רץ ברקע) — ייתפס בהרצה שלו.")

    if last_idx_ok_m:
        lines.append(f"קובץ האינדקס ({last_idx_ok_m.group(1)}MB) הועלה ל-R2 בהצלחה — האתר יתעדכן תוך כשעה.")
    elif idx_fail_any:
        lines.append("אזהרה: העלאת קובץ האינדקס ל-R2 נכשלה סופית באחת הריצות — ודאו שהאתר מעודכן!")
    else:
        lines.append("אזהרה: לא נמצאה הודעת הצלחה/כישלון להעלאת קובץ האינדקס.")

    success = dl_errors_total == 0 and r2_errors_total == 0 and not idx_fail_any
    status = "תקין: כל ריצות ההורדה היום הצליחו במלואן." if success else "אזהרה: לא כל ריצות ההורדה היום הצליחו במלואן — ראו פירוט למטה."
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
