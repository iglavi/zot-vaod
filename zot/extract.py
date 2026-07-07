"""חילוץ טקסט ומטא-דאטה מקבצי פסקי דין.

תומך גם ב-.docx (הפורמט האמיתי מאתר נט-המשפט) וגם ב-.txt (גיבוי/בדיקות).
מחלץ מגוף המסמך פרטים שאינם קיימים בקובץ ה-CSV: שם השופט/ת ותאריך ההחלטה.
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import HEB_MONTHS

_MONTHS_ALT = "|".join(HEB_MONTHS)

# "לפני כב' השופטת רוני סלע" / "לפני כבוד הרשם ..." וכד'
_JUDGE_RE = re.compile(r"לפנ[יי]\s+כב(?:ו?ד|['׳])?\s*(.{0,70})")
# תבנית תאריך לועזי בתוך גוף פסק הדין: "01 ינואר 2026"
_DATE_RE = re.compile(r"(\d{1,2})\s+(" + _MONTHS_ALT + r")\s+(\d{4})")
# מילים שמסמנות את סוף שם השופט/ת (תארים, תפקידי צדדים, מונחי פתיח)
_JUDGE_STOP = re.compile(
    r"העתק|פסק[\s\-]?דין|החלט|בעניין|בין\b|נגד|נ['׳]|מיום|"
    r"מבקש|משיב|עורר|מערער|תוב[ ע]|נתבע|עות[ר]|המבקש|בקשה|רקע|"
    r"ת[\"״]?א|\d|\n"
)


def read_text(path: str | Path) -> str:
    """קורא טקסט מלא מקובץ pdf/docx/txt. מחזיר מחרוזת ריקה במקרה כשל."""
    p = Path(path)
    suffix = p.suffix.lower()
    try:
        if suffix in (".docx", ".doc"):
            import docx  # python-docx

            document = docx.Document(str(p))
            parts = [para.text for para in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text:
                            parts.append(cell.text)
            return "\n".join(t for t in parts if t and t.strip())
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def extract_judge(text: str) -> str:
    """מחלץ את שם השופט/ת (כולל תואר) משורת 'לפני כב\'...'."""
    if not text:
        return ""
    m = _JUDGE_RE.search(text)
    if not m:
        return ""
    seg = m.group(1)
    seg = _JUDGE_STOP.split(seg)[0]
    seg = re.sub(r"\s+", " ", seg).strip(" .,:-‏‎")
    return seg


def extract_decision_date(text: str) -> str:
    """מחלץ את תאריך ההחלטה (הלועזי) ומחזיר ISO 'YYYY-MM-DD', או ''."""
    if not text:
        return ""
    m = _DATE_RE.search(text)
    if not m:
        return ""
    day = int(m.group(1))
    month = HEB_MONTHS[m.group(2)]
    year = int(m.group(3))
    try:
        return f"{year:04d}-{month:02d}-{day:02d}"
    except Exception:
        return ""


def filed_date_from_case(case_number: str) -> str:
    """גוזר תאריך פתיחה משוער ממספר התיק (למשל 49000-12-25 -> 2025-12-01)."""
    if not case_number:
        return ""
    parts = str(case_number).strip().split("-")
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        mm, yy = int(parts[1]), parts[2]
        if 1 <= mm <= 12 and len(yy) == 2:
            return f"20{yy}-{mm:02d}-01"
    return ""
