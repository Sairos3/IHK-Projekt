import re
from pathlib import Path
from rapidfuzz import fuzz

from wareneingang.db import fetch_invoice_lines_by_customer, fetch_delivery_lines_by_customer
from wareneingang.status import build_status
from wareneingang.ocr import extract_qty_under_menge_header

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

    m = QTY_RE.search(line)
    if not m:
        try:
            idx = lines.index(line)
            if idx + 1 < len(lines):
                m = QTY_RE.search(line + " " + lines[idx + 1])
        except ValueError:
            pass

    if not m:
        return 0.0, ""

    qty = float(m.group(1).replace(",", "."))
    item_m = ITEM_RE.search(line)
    item_no = item_m.group(1) if item_m else ""
    return qty, item_no


def deliveries_from_lieferschein_text(customer_no: str, ocr_text: str) -> list[dict]:
    invoices = fetch_invoice_lines_by_customer(customer_no)
    deliveries = fetch_delivery_lines_by_customer(customer_no)

    status_rows = build_status(invoices, deliveries)
    open_rows = [r for r in status_rows if r["status"] != "OK" and float(r["open_qty"]) > 0]

    wanted_descs = []
    seen = set()
    for r in open_rows:
        desc = r["invoice_description"]
        key = desc.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        wanted_descs.append(desc)

    new_delivery_lines = []
    for desc in wanted_descs:
        found_qty, item_no = _extract_qty_near(desc, ocr_text)
        if found_qty <= 0:
            continue

        new_delivery_lines.append({
            "customer_no": customer_no,
            "item_number": item_no,
            "description": desc,   # canonical invoice desc
            "qty": float(found_qty),
        })

    return new_delivery_lines


def deliveries_from_lieferschein_file(customer_no: str, ocr_text: str, file_path: str) -> list[dict]:
    """
    PHOTO strategy:
    - If image (jpg/png): read qty from 'Menge' column ROI (works for handwriting).
    - Only auto-assign if exactly ONE open item exists for that customer.
    - Clamp qty to open_qty to avoid mistakenly reading header '100,00'.
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

    p = Path(file_path)
    if p.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        qty = extract_qty_under_menge_header(file_path)

        # Only if exactly one open item exists
        if qty > 0 and len(wanted_descs) == 1:
            open_qty = float(open_rows[0]["open_qty"]) if open_rows else qty
            qty = min(qty, open_qty)  # clamp (prevents header '100,00' mistakes)

            return [{
                "customer_no": customer_no,
                "item_number": "",
                "description": wanted_descs[0],
                "qty": float(qty),
            }]

    # fallback: printed text matching (PDF / clean OCR)
    return deliveries_from_lieferschein_text(customer_no, ocr_text)