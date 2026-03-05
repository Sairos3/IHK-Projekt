# src/wareneingang/pipeline.py
import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import pdfplumber
from rapidfuzz import fuzz

from wareneingang.config import FUZZY_THRESHOLD
from wareneingang.detect import detect_text_pdf
from wareneingang.ocr import ocr_pdf_to_text, ocr_image_to_text


# -------------------------
# Models
# -------------------------
@dataclass
class InvoiceLine:
    customer_no: str
    description: str
    qty: float


@dataclass
class DeliveryLine:
    customer_no: str
    item_number: str
    description: str
    qty: float

def extract_customer_no(text: str) -> str:
    t = " ".join(text.replace("\u00a0", " ").split())
    m = re.search(r"Kundennummer\b.*?([0-9]{5,})", t, re.IGNORECASE)
    if m:
        return m.group(1)

    m = re.search(r"Kunden\s*[-]?\s*Nr\.?\s*[:.]?\s*([0-9]{5,})", t, re.IGNORECASE)
    if m:
        return m.group(1)

    return ""

def extract_lieferschein_no(text: str) -> str:
    t = " ".join(text.split())
    m = re.search(r"Lieferschein\s*Nr\.?\s*[:.]?\s*([0-9]{4,})", t, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""

def extract_pdf_text_auto(pdf_path: str) -> str:
    det = detect_text_pdf(pdf_path)
    if det.is_text_pdf:
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    return ocr_pdf_to_text(pdf_path)

def extract_match_key(text: str) -> str:
    cust = extract_customer_no(text)
    if cust:
        return f"CUST:{cust}"

    ls = extract_lieferschein_no(text)
    if ls:
        return f"LS:{ls}"

    return ""

# -------------------------
# Invoice extraction
# -------------------------
def extract_invoice_lines(pdf_path: str) -> List[InvoiceLine]:
    """
    BackFlow invoice example (from your PDFs):
    1 Bürositzkissen 100 Stk. 125,00 12.500,00
    Kundennummer is present on invoice PDFs. :contentReference[oaicite:3]{index=3} :contentReference[oaicite:4]{index=4}
    """
    text = extract_pdf_text_auto(pdf_path)
    customer_no = extract_customer_no(text)

    row_re = re.compile(
        r"^\s*\d+\s+(.+?)\s+(\d+(?:[.,]\d+)?)\s+Stk\.\s+",
        re.IGNORECASE
    )

    lines: List[InvoiceLine] = []
    for line in text.splitlines():
        m = row_re.match(line)
        if not m:
            continue
        desc = m.group(1).strip()
        qty = float(m.group(2).replace(",", "."))
        lines.append(InvoiceLine(customer_no=customer_no, description=desc, qty=qty))

    return lines


def extract_invoice_lines_dict(path: str) -> List[Dict]:
    return [{"customer_no": x.customer_no, "description": x.description, "qty": x.qty}
            for x in extract_invoice_lines(path)]


# -------------------------
# Delivery extraction (PDF or image)
# -------------------------
def extract_delivery_text_any(path: str) -> str:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        return ocr_pdf_to_text(path)
    return ocr_image_to_text(path)


def extract_delivery_lines_any(path: str) -> List[DeliveryLine]:
    """
    Lieferschein photo/PDF shows:
    Kunden-Nr.: 123456789 and a row:
    1 B-3025-078 Bürositzkissen 100,00 Stk. :contentReference[oaicite:5]{index=5}
    """
    text = extract_delivery_text_any(path)
    customer_no = extract_customer_no(text)

    # tolerant pattern that works across messy OCR whitespace/newlines
    row_re = re.compile(
        r"(?s)\b(\d+)\s+([A-Z0-9]{1,}-[0-9]{1,}-[0-9]{1,}|[A-Z0-9\-]{5,})\s+(.+?)\s+(\d+(?:[.,]\d+)?)\s*(?:Stk\.?|Stk)\b",
        re.IGNORECASE
    )

    lines = []
    for m in row_re.finditer(text):
        item = m.group(2).strip().upper()
        desc = " ".join(m.group(3).split()).strip()
        qty = float(m.group(4).replace(",", "."))
        lines.append({
            "customer_no": customer_no,
            "item_number": item,
            "description": desc,
            "qty": qty,
        })
    return lines

def extract_delivery_lines_dict(path: str):
    """
    Returns list[dict] for DB insert.
    Supports .pdf + .jpg/.jpeg/.png
    """
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        text = ocr_pdf_to_text(path)
    else:
        text = ocr_image_to_text(path)

    customer_no = extract_customer_no(text)

    # Save OCR debug so you can inspect it if parsing fails (IHK-friendly)
    Path("output").mkdir(exist_ok=True)
    Path("output/last_ocr_delivery.txt").write_text(text, encoding="utf-8", errors="ignore")

    # tolerant multi-line regex (OCR may insert line breaks)
    row_re = re.compile(
        r"(?s)\b(\d+)\s+([A-Z0-9]{1,}-[0-9]{1,}-[0-9]{1,}|[A-Z0-9\-]{5,})\s+(.+?)\s+(\d+(?:[.,]\d+)?)\s*(?:Stk\.?|Stk)\b",
        re.IGNORECASE
    )

    lines = []
    for m in row_re.finditer(text):
        item = m.group(2).strip().upper()
        desc = " ".join(m.group(3).split()).strip()
        qty = float(m.group(4).replace(",", "."))
        lines.append({
            "customer_no": customer_no,
            "item_number": item,
            "description": desc,
            "qty": qty,
        })

    return lines

# -------------------------
# Matching (not quantity allocation — that belongs in status.py)
# Keep this simple; allocation is in build_status()
# -------------------------
def best_match_score(a: str, b: str) -> int:
    return fuzz.token_sort_ratio(a.lower(), b.lower())

def invoice_extract_for_import(path: str):
    text = extract_pdf_text_auto(path)

    from pathlib import Path
    Path("output").mkdir(exist_ok=True)
    Path("output/last_invoice_text.txt").write_text(text, encoding="utf-8", errors="ignore")

    match_key = extract_match_key(text)
    lines = extract_invoice_lines_dict(path)
    for l in lines:
        l["match_key"] = match_key
    return match_key, lines


from pathlib import Path
from wareneingang.ocr import ocr_pdf_to_text, ocr_image_to_text
from wareneingang.delivery_matcher import deliveries_from_lieferschein_text

def delivery_extract_for_import(path: str):
    p = Path(path)
    text = ocr_pdf_to_text(path) if p.suffix.lower() == ".pdf" else ocr_image_to_text(path)

    # debug file (so you can prove OCR in IHK)
    Path("output").mkdir(exist_ok=True)
    Path("output/last_ocr_delivery.txt").write_text(text, encoding="utf-8", errors="ignore")

    customer_no = extract_customer_no(text)

    # fallback: if customer missing, keep separate (no mixing)
    if customer_no:
        match_key = f"CUST:{customer_no}"
        lines = deliveries_from_lieferschein_text(customer_no, text)
    else:
        ls = extract_lieferschein_no(text)
        match_key = f"LS:{ls}" if ls else ""
        lines = []  # no customer => we don't allocate automatically

    for l in lines:
        l["match_key"] = match_key

    return match_key, lines