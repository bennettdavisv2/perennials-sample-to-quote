"""NetSuite-style ERP mock: inventory by dye lot, sales orders (samples, holds, CFA), customers."""
from __future__ import annotations

import streamlit as st

from .common import acct_name, order_lines, system_header, table, wf


def render():
    w = wf()
    system_header("erp", "ERP", "NetSuite-style mock · items, price, inventory by dye lot, orders")
    t = st.tabs(["Inventory", "Sales orders", "Customers"])
    with t[0]:
        st.caption("Available = on hand − reserved. Holds from quotes show up here as reserved yardage, per dye lot.")
        table(w.erp.lots, {"SKU": "sku", "Fabric": "fabric", "Color": "color", "Status": "status", "Dye lot": "lot",
                           "On hand (yd)": "on_hand", "Reserved (yd)": "reserved",
                           "Available (yd)": lambda l: max(l["on_hand"] - l["reserved"], 0), "List $/yd": "list_price"},
              money_cols=["List $/yd"], height=35 * (len(w.erp.lots) + 1) + 3)
    with t[1]:
        kinds = st.multiselect("Type", ["Sample", "Reservation", "CFA"], default=["Sample", "Reservation", "CFA"])
        orders = sorted((s for s in w.erp.sales_orders if s["type"] in kinds), key=lambda s: s["created"], reverse=True)
        cust = {c["id"]: c["name"] for c in w.erp.customers.values()}
        table(orders, {"Order": "id", "Type": "type", "Customer": lambda s: cust.get(s["customer"], s["customer"]),
                       "For quote (CRM)": lambda s: s.get("quote_id") or "", "Status": "status", "Lines": order_lines,
                       "Created": lambda s: f"{s['created']:%b %d}",
                       "Hold until": lambda s: f"{s['hold_expires']:%b %d}" if s.get("hold_expires") else ""})
    with t[2]:
        st.caption("Created on the first order, keyed to the CRM account (externalId), so the two systems stay linked.")
        table(list(w.erp.customers.values()), {"Customer": "id", "Name": "name",
                                               "CRM account (externalId)": "crm_account_id",
                                               "CRM name": lambda c: acct_name(w, c["crm_account_id"])})
