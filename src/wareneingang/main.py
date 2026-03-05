from datetime import datetime
from pathlib import Path
from wareneingang.pipeline import invoice_extract_for_import, delivery_extract_for_import
from wareneingang.logger import setup_logger
from wareneingang.db import init_db, fetch_all_invoice_lines, fetch_all_delivery_lines
from wareneingang.importer import import_folder
from wareneingang.pipeline import extract_invoice_lines_dict, extract_delivery_lines_dict
from wareneingang.status import build_status
from wareneingang.export_excel import export_status_xlsx


def main():
    logger = setup_logger()
    init_db()

    # 1) Import new files from folders (skip duplicates via sha256)
    import_folder("input/rechnung", "invoice", invoice_extract_for_import, logger)
    import_folder("input/lieferschein", "delivery", delivery_extract_for_import, logger)
    # 2) Build status from DB (always up to date, no duplicates)
    invoices = fetch_all_invoice_lines()
    deliveries = fetch_all_delivery_lines()

    logger.info(f"DB totals: invoices={len(invoices)} delivery_lines={len(deliveries)}")

    status_rows = build_status(invoices, deliveries)

    # 3) Export Excel
    Path("output").mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"output\\Wareneingang_Status_{ts}.xlsx"
    export_status_xlsx(status_rows, out_path)

    logger.info(f"Excel exported: {out_path}")


if __name__ == "__main__":
    main()