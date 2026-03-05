# src/wareneingang/logger.py

import logging
from pathlib import Path

LOG_FILE = Path("logs/wareneingang.log")

def setup_logger():
    LOG_FILE.parent.mkdir(exist_ok=True)

    logger = logging.getLogger("wareneingang")
    logger.setLevel(logging.INFO)

    # file log
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )
    file_handler.setFormatter(file_format)

    # console log
    console_handler = logging.StreamHandler()
    console_format = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_format)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger