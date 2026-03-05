# src/wareneingang/detect.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pdfplumber


@dataclass
class PdfDetectionResult:
    is_text_pdf: bool
    avg_text_length: float
    pages_checked: int


def detect_text_pdf(pdf_path: str, pages_to_check: int = 2, min_avg_chars: int = 40) -> PdfDetectionResult:
    """
    Heuristic:
    - Extract text from first N pages using pdfplumber
    - If average extracted characters >= min_avg_chars => text-based PDF
    Else => probably scanned image PDF
    """
    texts = []

    with pdfplumber.open(pdf_path) as pdf:
        n = min(pages_to_check, len(pdf.pages))
        for i in range(n):
            t = pdf.pages[i].extract_text() or ""
            # normalize whitespace
            t = " ".join(t.split())
            texts.append(t)

    if not texts:
        return PdfDetectionResult(is_text_pdf=False, avg_text_length=0.0, pages_checked=0)

    avg_len = sum(len(t) for t in texts) / len(texts)
    return PdfDetectionResult(
        is_text_pdf=avg_len >= min_avg_chars,
        avg_text_length=avg_len,
        pages_checked=len(texts),
    )