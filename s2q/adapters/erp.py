"""Mock ERP (stands in for NetSuite).

Source of truth for: items, item status, list price + price rules, inventory by dye
lot, sample orders, and reservations (pending sales orders).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from ..audit import AuditLog
from ..data import PricingConfig
from ..pricing import price_line


class MockERP:
    def __init__(self, lots: list[dict], pricing: PricingConfig, log: AuditLog):
        self.lots = [dict(l) for l in lots]
        self.pricing = pricing
        self.log = log
        self.sales_orders: list[dict] = []
        self.customers: dict[str, dict] = {}  # crm account id -> erp customer
        self._seq = defaultdict(int)

    def _id(self, prefix):
        self._seq[prefix] += 1
        return f"{prefix}-{self._seq[prefix]:04d}"

    # ---------- items ----------
    @staticmethod
    def _rollup(lots: list[dict]) -> list[dict]:
        out: dict[str, dict] = {}
        for l in lots:
            it = out.setdefault(l["sku"], {k: l[k] for k in ("sku", "fabric", "color", "status", "list_price")}
                                | {"available": 0.0, "on_hand": 0.0})
            it["available"] += max(l["on_hand"] - l["reserved"], 0)
            it["on_hand"] += l["on_hand"]
        return list(out.values())

    def items(self) -> list[dict]:
        """One row per SKU (status, price, total availability across its dye lots)."""
        return self._rollup(self.lots)

    def get_item(self, sku: str) -> dict | None:
        rows = self._rollup(self.lots_for(sku))
        return rows[0] if rows else None

    def lots_for(self, sku: str) -> list[dict]:
        return [l for l in self.lots if l["sku"] == sku]

    # ---------- customers ----------
    def upsert_customer(self, account: dict) -> str:
        if account["id"] not in self.customers:
            cid = self._id("CUST")
            self.customers[account["id"]] = {"id": cid, "crm_account_id": account["id"],
                                             "name": account["name"], "price_level": account.get("price_level")}
            self.log.record("ERP", "Create customer", f"{cid} for {account['name']} (CRM {account['id']})",
                            "NetSuite REST: POST /record/v1/customer (externalId = CRM Account Id)")
        return self.customers[account["id"]]["id"]

    # ---------- pricing ----------
    def price(self, sku: str, yards: float, is_trade: bool) -> dict:
        item = self.get_item(sku)
        p = price_line(item["list_price"], yards, is_trade, self.pricing)
        self.log.record("ERP", "Price line", f"{sku} {yards} yd, {'trade' if is_trade else 'non-trade'} -> ${p['line_total']:,.2f}",
                        "NetSuite: price level lookup / RESTlet for quote pricing")
        return p

    # ---------- inventory ----------
    def allocate(self, sku: str, yards: float) -> dict:
        """Propose a dye-lot allocation (does not reserve).

        Prefers a single lot that covers the whole line (dye lots can differ visibly,
        so a job should come from one lot). Falls back to splitting across lots.
        """
        lots = [dict(l, available=max(l["on_hand"] - l["reserved"], 0)) for l in self.lots_for(sku)]
        total = sum(l["available"] for l in lots)
        single = sorted([l for l in lots if l["available"] >= yards], key=lambda l: l["available"])
        if single:
            return {"lines": [{"lot": single[0]["lot"], "yards": yards}], "split": False,
                    "short": 0.0, "available": total}
        alloc, remaining = [], yards
        for l in sorted(lots, key=lambda l: -l["available"]):
            if remaining <= 0 or l["available"] <= 0:
                continue
            take = min(l["available"], remaining)
            alloc.append({"lot": l["lot"], "yards": take})
            remaining -= take
        return {"lines": alloc, "split": len(alloc) > 1, "short": round(max(remaining, 0), 2), "available": total}

    def create_reservation(self, customer_id: str, quote_id: str, lines: list[dict], now: datetime) -> dict:
        """Pending sales order that holds yardage against specific dye lots."""
        so = {"id": self._id("SO"), "type": "Reservation", "customer": customer_id, "quote_id": quote_id,
              "status": "Pending Approval (hold)", "created": now,
              "hold_expires": now + timedelta(days=self.pricing.hold_days), "lines": lines}
        for ln in lines:
            for a in ln["allocation"]:
                lot = next(l for l in self.lots if l["sku"] == ln["sku"] and l["lot"] == a["lot"])
                lot["reserved"] += a["yards"]
        self.sales_orders.append(so)
        desc = "; ".join(f"{ln['sku']} " + ", ".join(f"{a['yards']} yd lot {a['lot']}" for a in ln["allocation"]) for ln in lines)
        self.log.record("ERP", "Reserve inventory", f"{so['id']} for {quote_id}: {desc}; hold until {so['hold_expires']:%Y-%m-%d}",
                        "NetSuite REST: POST /record/v1/salesOrder (orderStatus = Pending Approval, inventory detail by lot)")
        return so

    def release_reservation(self, so_id: str, reason: str):
        so = next(s for s in self.sales_orders if s["id"] == so_id)
        if so["status"].startswith("Released"):
            return
        for ln in so["lines"]:
            for a in ln["allocation"]:
                lot = next(l for l in self.lots if l["sku"] == ln["sku"] and l["lot"] == a["lot"])
                lot["reserved"] -= a["yards"]
        so["status"] = f"Released ({reason})"
        self.log.record("ERP", "Release reservation", f"{so_id}: {reason}",
                        "NetSuite REST: PATCH /record/v1/salesOrder/{id} (close lines)")

    def create_cfa_order(self, customer_id: str, quote_id: str, alloc_plan: list[dict], ship_to: str,
                         now: datetime) -> dict:
        """CFA (cutting for approval): a small cutting from each lot being held, so the customer
        approves the actual dye lot before ordering."""
        so = {"id": self._id("CFA"), "type": "CFA", "customer": customer_id, "quote_id": quote_id,
              "status": "Pending Fulfillment", "created": now, "ship_to": ship_to,
              "lines": [{"sku": l["sku"], "lot": a["lot"], "qty": 1, "uom": "cutting"}
                        for l in alloc_plan for a in l["allocation"]]}
        self.sales_orders.append(so)
        self.log.record("ERP", "Create CFA order", f"{so['id']} for {quote_id}: " +
                        ", ".join(f"{ln['sku']} lot {ln['lot']}" for ln in so["lines"]),
                        "NetSuite REST: POST /record/v1/salesOrder (custom form = CFA, $0, lot-specific inventory detail)")
        return so

    def create_sample_order(self, customer_id: str, skus: list[str], ship_to: str, now: datetime) -> dict:
        so = {"id": self._id("SMP"), "type": "Sample", "customer": customer_id, "status": "Pending Fulfillment",
              "created": now, "lines": [{"sku": s, "qty": 1, "uom": "memo swatch"} for s in skus], "ship_to": ship_to}
        self.sales_orders.append(so)
        self.log.record("ERP", "Create sample order", f"{so['id']}: {', '.join(skus)}",
                        "NetSuite REST: POST /record/v1/salesOrder (custom form = Sample, $0 price level)")
        return so
