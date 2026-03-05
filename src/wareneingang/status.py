from collections import defaultdict
from rapidfuzz import fuzz
from wareneingang.config import FUZZY_THRESHOLD


def build_status(invoice_lines, delivery_lines):
    """
    - Separate by customer_no (no cross-customer matching)
    - Quantity allocation: delivered qty is consumed so it can't satisfy multiple invoices
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

        # remaining qty per delivery line (consumption)
        remaining = [float(d["qty"]) for d in dels]

        # process invoices oldest first (optional)
        invs = sorted(invs, key=lambda x: x.get("created_at", ""))

        for inv in invs:
            inv_desc = inv["description"]
            inv_qty = float(inv["qty"])

            best_idx = None
            best_score = -1

            for idx, d in enumerate(dels):
                if remaining[idx] <= 0:
                    continue
                score = fuzz.token_sort_ratio(inv_desc.lower(), d["description"].lower())
                if score > best_score:
                    best_score = score
                    best_idx = idx

            if best_idx is None or best_score < FUZZY_THRESHOLD:
                out_rows.append({
                    "customer_no": customer_no,
                    "item_number": "",
                    "invoice_description": inv_desc,
                    "delivery_description": "",
                    "qty_ordered": inv_qty,
                    "qty_delivered": 0.0,
                    "open_qty": inv_qty,
                    "status": "PARKED",
                })
                continue

            d = dels[best_idx]
            used = min(inv_qty, remaining[best_idx])
            remaining[best_idx] -= used

            open_qty = max(inv_qty - used, 0.0)
            status = "OK" if open_qty == 0 else "PARTIAL" if used > 0 else "PARKED"

            out_rows.append({
                "customer_no": customer_no,
                "item_number": d.get("item_number") or "",
                "invoice_description": inv_desc,
                "delivery_description": d["description"],
                "qty_ordered": inv_qty,
                "qty_delivered": used,
                "open_qty": open_qty,
                "status": status,
            })

    return out_rows