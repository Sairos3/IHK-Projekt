# src/wareneingang/importer.py
import hashlib
from pathlib import Path
from datetime import datetime

from wareneingang.db import (
    file_exists,
    insert_file,
    insert_invoice_lines,
    insert_delivery_lines,
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def import_any_file(path: Path, doc_type: str, extract_fn, logger):
    """
    extract_fn(path_str) -> (match_key: str, lines: list[dict])
    """
    digest = sha256_file(path)

    if file_exists(digest):
        logger.info(f"SKIP duplicate: {path.name}")
        return

    match_key, lines = extract_fn(str(path))
    created_at = datetime.now().isoformat(timespec="seconds")

    file_id = insert_file(str(path), digest, doc_type, created_at, match_key)

    logger.info(f"IMPORTED {doc_type}: {path.name} (match_key={match_key}, lines={len(lines)})")

    if doc_type == "invoice":
        insert_invoice_lines(file_id, lines)
    elif doc_type == "delivery":
        insert_delivery_lines(file_id, lines)
    else:
        raise ValueError(f"Unknown doc_type: {doc_type}")


def import_folder(folder: str, doc_type: str, extract_fn, logger):
    p = Path(folder)
    p.mkdir(parents=True, exist_ok=True)

    allowed = {".pdf", ".jpg", ".jpeg", ".png"} if doc_type == "delivery" else {".pdf"}

    files = sorted([x for x in p.iterdir() if x.is_file() and x.suffix.lower() in allowed])
    for f in files:
        import_any_file(f, doc_type, extract_fn, logger)