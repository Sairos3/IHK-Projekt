import re
from rapidfuzz import fuzz

from wareneingang.db import fetch_invoice_lines_by_customer, fetch_delivery_lines_by_customer
from wareneingang.status import build_status


QTY_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:Stk\.?|Stk)\b", re.IGNORECASE)
ITEM_RE = re.compile(r"\b([A-Z0-9]{2,}-[0-9]{2,}-[0-9]{2,}|[A-Z0-9\-]{6,})\b")


def _best_line_for_desc(desc: str, lines: list[str]) -> tuple[int, str]:
    best_score, best_line = -1, ""
    for line in lines:
        score = fuzz.token_set_ratio(desc.lower(), line.lower())
        if score > best_score:
            best_score, best_line = score, line
    return best_score, best_line


def _extract_qty_near(desc: str, ocr_text: str) -> tuple[float, str]:
    lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]
    score, line = _best_line_for_desc(desc, lines)

    if score < 70:
        return 0.0, ""

    item_no = ""
    try:
        idx = lines.index(line)
    except ValueError:
        return 0.0, ""

    # Search current line + next few lines together
    window_parts = []
    for offset in range(0, 4):   # line + next 3 lines
        if idx + offset < len(lines):
            window_parts.append(lines[idx + offset])

    window_text = " ".join(window_parts)

    m = QTY_RE.search(window_text)
    if not m:
        return 0.0, ""

    qty = float(m.group(1).replace(",", "."))
    item_m = ITEM_RE.search(window_text)
    if item_m:
        item_no = item_m.group(1)

    return qty, item_no


def deliveries_from_lieferschein_file(customer_no: str, ocr_text: str, file_path: str) -> list[dict]:
    """
    Simplified version:
    - No handwriting detection
    - Only OCR text matching
    """

    invoices = fetch_invoice_lines_by_customer(customer_no)
    deliveries = fetch_delivery_lines_by_customer(customer_no)

    status_rows = build_status(invoices, deliveries)
    open_rows = [r for r in status_rows if r["status"] != "OK" and float(r["open_qty"]) > 0]

    wanted_descs = []
    seen = set()

    for r in open_rows:
        desc = r["invoice_description"]
        k = desc.lower().strip()
        if k in seen:
            continue
        seen.add(k)
        wanted_descs.append(desc)

    new_delivery_lines = []

    for desc in wanted_descs:
        found_qty, item_no = _extract_qty_near(desc, ocr_text)

        if found_qty <= 0:
            continue

        new_delivery_lines.append({
            "customer_no": customer_no,
            "item_number": item_no,
            "description": desc,
            "qty": float(found_qty),
        })

    return new_delivery_lines