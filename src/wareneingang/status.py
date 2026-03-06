from collections import defaultdict
from rapidfuzz import fuzz
from wareneingang.config import FUZZY_THRESHOLD


def build_status(invoice_lines, delivery_lines):
    """
    - Separate by customer_no
    - One invoice can consume multiple deliveries
    - Deliveries that arrive first appear as PARKED_DELIVERY
    """

    inv_by_cust = defaultdict(list)
    del_by_cust = defaultdict(list)

    for inv in invoice_lines:
        inv_by_cust[inv.get("customer_no", "")].append(inv)

    for d in delivery_lines:
        del_by_cust[d.get("customer_no", "")].append(d)

    out_rows = []

    for customer_no, invs in inv_by_cust.items():

        dels = del_by_cust.get(customer_no, [])

        # Track remaining quantities for delivery rows
        remaining = [float(d["qty"]) for d in dels]

        # Process invoices oldest first
        invs = sorted(invs, key=lambda x: x.get("created_at", ""))

        for inv in invs:

            inv_desc = inv["description"]
            inv_qty = float(inv["qty"])

            qty_needed = inv_qty
            qty_delivered_total = 0.0

            best_delivery_desc = ""
            best_item_number = ""

            candidates = []

            for idx, d in enumerate(dels):

                if remaining[idx] <= 0:
                    continue

                score = fuzz.token_sort_ratio(
                    inv_desc.lower(),
                    d["description"].lower()
                )

                if score >= FUZZY_THRESHOLD:
                    candidates.append((idx, score, d))

            # Best matches first
            candidates.sort(key=lambda x: (-x[1], x[2].get("created_at", "")))

            for idx, score, d in candidates:

                if qty_needed <= 0:
                    break

                if remaining[idx] <= 0:
                    continue

                used = min(qty_needed, remaining[idx])

                remaining[idx] -= used
                qty_needed -= used
                qty_delivered_total += used

                if not best_delivery_desc:
                    best_delivery_desc = d["description"]

                if not best_item_number:
                    best_item_number = d.get("item_number") or ""

            open_qty = max(inv_qty - qty_delivered_total, 0.0)

            if qty_delivered_total == 0:
                status = "PARKED_INVOICE"
            elif open_qty == 0:
                status = "OK"
            else:
                status = "PARTIAL"

            out_rows.append({
                "customer_no": customer_no,
                "item_number": best_item_number,
                "invoice_description": inv_desc,
                "delivery_description": best_delivery_desc,
                "qty_ordered": inv_qty,
                "qty_delivered": qty_delivered_total,
                "open_qty": open_qty,
                "status": status,
            })

        # AFTER invoices → add leftover deliveries
        for idx, d in enumerate(dels):

            if remaining[idx] <= 0:
                continue

            out_rows.append({
                "customer_no": customer_no,
                "item_number": d.get("item_number") or "",
                "invoice_description": "",
                "delivery_description": d["description"],
                "qty_ordered": 0.0,
                "qty_delivered": float(d["qty"]),
                "open_qty": remaining[idx],
                "status": "PARKED_DELIVERY",
            })

    return out_rows