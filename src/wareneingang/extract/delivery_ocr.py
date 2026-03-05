import pytesseract
from pdf2image import convert_from_path
import cv2
import numpy as np
import re


def extract_delivery_lines(pdf_path):

    pages = convert_from_path(
        pdf_path,
        dpi=300,
        poppler_path=r"C:\poppler\Library\bin"
    )

    text = ""

    for page in pages:

        img = cv2.cvtColor(np.array(page), cv2.COLOR_RGB2GRAY)

        _, img = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY)

        ocr = pytesseract.image_to_string(
            img,
            lang="deu"
        )

        text += ocr + "\n"

    pattern = re.compile(
        r"\d+\s+([A-Z0-9\-]+)\s+(.+?)\s+([\d,]+)\s+Stk",
        re.IGNORECASE
    )

    results = []

    for match in pattern.finditer(text):

        item_number = match.group(1)

        description = match.group(2).strip()

        qty = float(match.group(3).replace(",", "."))

        results.append({
            "item_number": item_number,
            "description": description,
            "qty": qty
        })

    return results