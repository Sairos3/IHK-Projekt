# src/wareneingang/ocr.py
from wareneingang.config import TESSERACT_CMD, OCR_LANG, POPPLER_PATH

def _preprocess(pil_img):
    import cv2
    import numpy as np

    img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # upscale (helps phone photos a lot)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    # denoise
    gray = cv2.bilateralFilter(gray, 9, 75, 75)

    # adaptive threshold (better for uneven lighting)
    th = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 10
    )
    return th

def _score_text(t: str) -> int:
    # choose OCR output that likely contains table lines
    s = 0
    if "Stk" in t or "stk" in t:
        s += 5
    # count digits (tables contain many digits)
    s += sum(ch.isdigit() for ch in t) // 10
    return s

def ocr_image_to_text(image_path: str, lang: str = None) -> str:
    import pytesseract
    from PIL import Image

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    use_lang = lang or OCR_LANG

    img = Image.open(image_path).convert("RGB")
    pre = _preprocess(img)

    # Try multiple page segmentation modes (photos vary a lot)
    configs = [
        "--oem 3 --psm 6 -c preserve_interword_spaces=1",
        "--oem 3 --psm 4 -c preserve_interword_spaces=1",
        "--oem 3 --psm 11 -c preserve_interword_spaces=1",
    ]

    best_text = ""
    best_score = -1
    for cfg in configs:
        t = pytesseract.image_to_string(pre, lang=use_lang, config=cfg)
        sc = _score_text(t)
        if sc > best_score:
            best_score = sc
            best_text = t

    return best_text

def ocr_pdf_to_text(pdf_path: str, lang: str = None) -> str:
    import pytesseract
    from pdf2image import convert_from_path

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    use_lang = lang or OCR_LANG

    pages = convert_from_path(pdf_path, dpi=300, poppler_path=POPPLER_PATH)
    texts = []
    for p in pages:
        pre = _preprocess(p)
        texts.append(pytesseract.image_to_string(pre, lang=use_lang, config="--oem 3 --psm 6"))
    return "\n".join(texts)

def extract_qty_under_menge_header(image_path: str) -> float:
    """
    Detect the 'Menge' header and OCR the entire column below it.
    Works for handwritten quantities.
    """
    import re
    import cv2
    import numpy as np
    import pytesseract
    from PIL import Image
    from pathlib import Path

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    img = Image.open(image_path).convert("RGB")
    bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    pre = _preprocess(img)

    data = pytesseract.image_to_data(
        pre,
        lang=OCR_LANG,
        config="--oem 3 --psm 6",
        output_type=pytesseract.Output.DICT
    )

    menge_box = None
    for i, txt in enumerate(data["text"]):
        if txt.strip().lower().startswith("menge"):
            menge_box = (
                data["left"][i],
                data["top"][i],
                data["width"][i],
                data["height"][i]
            )
            break

    if not menge_box:
        return 0.0

    x, y, w, h = menge_box
    H, W = pre.shape

    # column area under the header
    x1 = max(x - int(0.3 * w), 0)
    x2 = min(x + int(3.0 * w), W)

    y1 = y + int(1.2 * h)
    y2 = min(H, y + int(40 * h))   # go far down to include table rows

    roi = pre[y1:y2, x1:x2]

    Path("output").mkdir(exist_ok=True)
    cv2.imwrite("output/debug_qty_roi.png", roi)

    txt = pytesseract.image_to_string(
        roi,
        config="--psm 6 -c tessedit_char_whitelist=0123456789.,"
    )

    m = re.search(r"\d+(?:[.,]\d+)?", txt)

    if not m:
        return 0.0

    return float(m.group(0).replace(",", "."))

def extract_customer_no_from_lieferschein_image(image_path: str) -> str:
    """
    Robustly extract Kunden-Nr from the top-right header area of a Lieferschein photo.
    Works even if printed number is overwritten by handwriting.
    """
    import re
    import cv2
    import numpy as np
    import pytesseract
    from PIL import Image
    from pathlib import Path

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    img = Image.open(image_path).convert("RGB")
    bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]

    # top-right header area where Kunden-Nr is printed/written
    x1, x2 = int(0.58 * w), int(0.98 * w)
    y1, y2 = int(0.08 * h), int(0.30 * h)
    roi = bgr[y1:y2, x1:x2]

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # debug (optional but useful)
    Path("output").mkdir(exist_ok=True)
    cv2.imwrite("output/debug_customer_roi.png", roi)
    cv2.imwrite("output/debug_customer_thresh.png", th)

    txt = pytesseract.image_to_string(
        th,
        lang=OCR_LANG,
        config="--psm 6 -c tessedit_char_whitelist=0123456789"
    )

    m = re.search(r"([0-9]{5,})", txt)
    return m.group(1) if m else ""