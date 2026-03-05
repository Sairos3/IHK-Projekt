# src/wareneingang/pipeline.py
import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict
from wareneingang.db import fetch_known_customers
import pdfplumber
from rapidfuzz import fuzz

from wareneingang.detect import detect_text_pdf
from wareneingang.ocr import (
    ocr_pdf_to_text,
    ocr_image_to_text,
)
from wareneingang.delivery_matcher import deliveries_from_lieferschein_file


# -------------------------
# Models
# -------------------------
@dataclass
class InvoiceLine:
    customer_no: str
    description: str
    qty: float


# -------------------------
# Header extraction helpers
# -------------------------
def extract_customer_no(text: str) -> str:
    t = " ".join(text.replace("\u00a0", " ").split())

    # Rechnung: Kundennummer ... 12345
    m = re.search(r"Kundennummer\b.*?([0-9]{5,})", t, re.IGNORECASE)
    if m:
        return m.group(1)

    # Lieferschein: Kunden-Nr.: 12345 (OCR variants)
    m = re.search(r"Kunden\s*[-]?\s*Nr\.?\s*[:.]?\s*([0-9]{5,})", t, re.IGNORECASE)
    if m:
        return m.group(1)

    return ""


def extract_lieferschein_no(text: str) -> str:
    t = " ".join(text.split())
    m = re.search(r"Lieferschein\s*Nr\.?\s*[:.]?\s*([0-9]{4,})", t, re.IGNORECASE)
    return m.group(1) if m else ""


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
    text = extract_pdf_text_auto(pdf_path)
    customer_no = extract_customer_no(text)

    # Example row: "1 ICECREAM 50 Stk. ..."
    row_re = re.compile(
        r"^\s*\d+\s+(.+?)\s+(\d+(?:[.,]\d+)?)\s+Stk\.\s+",
        re.IGNORECASE
    )

    out: List[InvoiceLine] = []
    for line in text.splitlines():
        m = row_re.match(line)
        if not m:
            continue
        desc = m.group(1).strip()
        qty = float(m.group(2).replace(",", "."))
        out.append(InvoiceLine(customer_no=customer_no, description=desc, qty=qty))

    return out


def extract_invoice_lines_dict(path: str) -> List[Dict]:
    return [{"customer_no": x.customer_no, "description": x.description, "qty": x.qty}
            for x in extract_invoice_lines(path)]


def invoice_extract_for_import(path: str):
    text = extract_pdf_text_auto(path)
    Path("output").mkdir(exist_ok=True)
    Path("output/last_invoice_text.txt").write_text(text, encoding="utf-8", errors="ignore")

    match_key = extract_match_key(text)
    lines = extract_invoice_lines_dict(path)
    for l in lines:
        l["match_key"] = match_key
    return match_key, lines


# -------------------------
# Delivery import (NEW STRATEGY)
# -------------------------
def delivery_extract_for_import(path: str):
    p = Path(path)

    # OCR full text
    text = ocr_pdf_to_text(path) if p.suffix.lower() == ".pdf" else ocr_image_to_text(path)

    Path("output").mkdir(exist_ok=True)
    Path("output/last_ocr_delivery.txt").write_text(text, encoding="utf-8", errors="ignore")

    # NEW: do not "extract" customer from image
    # Instead: match against known invoice customers
    known_customers = fetch_known_customers()

    # Normalize text to digits/spaces only (tolerates OCR junk like 9O99O9)
    digits_only = "".join(ch if ch.isdigit() else " " for ch in text)

    customer_no = ""
    for cust in known_customers:
        if cust and cust in digits_only:
            customer_no = cust
            break

    if customer_no:
        match_key = f"CUST:{customer_no}"
        lines = deliveries_from_lieferschein_file(customer_no, text, path)
    else:
        ls = extract_lieferschein_no(text)
        match_key = f"LS:{ls}" if ls else ""
        lines = []

    for l in lines:
        l["match_key"] = match_key

    return match_key, lines


# -------------------------
# Optional helper used elsewhere
# -------------------------
def best_match_score(a: str, b: str) -> int:
    return fuzz.token_sort_ratio(a.lower(), b.lower())