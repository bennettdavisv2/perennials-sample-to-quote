"""Shared state and helpers for the demo pages.

One Workflow lives in the Streamlit session and every page (website, CRM, ERP, old vs new,
ops console) reads and writes it, the way the real systems would share data through the
integration layer. It starts seeded: the 21 workbook requests are already processed, so
the CRM and ERP have history and Dana Ruiz is a known customer.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from s2q.workflow import Workflow

PAGES: dict = {}  # name -> st.Page, filled in by app.py so pages can link to each other

SYSTEM_STYLE = {
    "site": ("#faf8f4", "#2b2b2b", "#e7e2d9"),
    "crm": ("#0b5cab", "#ffffff", "#0b5cab"),
    "erp": ("#2b3a4a", "#ffffff", "#2b3a4a"),
    "compare": ("#f2f4f7", "#1d2939", "#d0d5dd"),
}


def md(text) -> str:
    """Escape $ so Streamlit markdown doesn't render prices as LaTeX."""
    return str(text).replace("$", "\\$")


def money(x) -> str:
    return f"${x:,.2f}"


def wf() -> Workflow:
    if "wf" not in st.session_state:
        w = Workflow(mode=st.session_state.get("mode", "auto"))
        w.process_all()  # seeded history
        st.session_state.wf = w
    return st.session_state.wf


def reset():
    for k in ("wf", "cart", "site_view", "site_fabric", "last_order", "selected", "last_email"):
        st.session_state.pop(k, None)


def system_header(kind: str, title: str, subtitle: str):
    """A colored bar so it's obvious which system you're looking at (no real logos or branding)."""
    bg, fg, border = SYSTEM_STYLE[kind]
    st.markdown(
        f"<div style='background:{bg};color:{fg};border:1px solid {border};border-radius:8px;"
        f"padding:12px 18px;margin-bottom:12px'>"
        f"<span style='font-size:1.35rem;font-weight:700;letter-spacing:.02em'>{title}</span>"
        f"<span style='opacity:.8;margin-left:12px'>{subtitle}</span></div>",
        unsafe_allow_html=True)


def swatch(hex_color: str, size: int = 28, label: str = "") -> str:
    tip = f" title='{label}'" if label else ""
    return (f"<span{tip} style='display:inline-block;width:{size}px;height:{size}px;border-radius:4px;"
            f"background:{hex_color};border:1px solid #0002;margin-right:4px;vertical-align:middle'></span>")


def table(rows: list[dict], cols: dict, money_cols=(), height="auto", key=None, select=False):
    """Show rows with friendly column names (cols maps label -> key or function).
    With select=True, returns the clicked row index (or None)."""
    if not rows:
        st.caption("No records yet.")
        return None
    d = pd.DataFrame([{label: (f(r) if callable(f) else r.get(f)) for label, f in cols.items()} for r in rows])
    kw = {"on_select": "rerun", "selection_mode": "single-row", "key": key} if select else {}
    ev = st.dataframe(d, hide_index=True, width="stretch", height=height,
                      column_config={c: st.column_config.NumberColumn(format="$%.2f") for c in money_cols}, **kw)
    return ev.selection.rows[0] if select and ev.selection.rows else None


def open_reviews(w, rid: str | None = None) -> list[dict]:
    return [r for r in w.reviews if r["status"] == "Open" and (rid is None or r["request"] == rid)]


def review_buttons(w, rv: dict, where: str):
    a, b = st.columns(2)
    if a.button("Approve", key=f"a-{where}-{rv['id']}", type="primary", width="stretch",
                help=f"Approve: {rv['proposed']}"):
        w.approve(rv["id"])
        st.rerun()
    if b.button("Reject", key=f"r-{where}-{rv['id']}", width="stretch"):
        w.reject(rv["id"])
        st.rerun()


def reasons(rv: dict) -> list[str]:
    text = rv["reason"].split(": ", 1)[1] if rv["action"] == "send_quote" else rv["reason"]
    return [p.strip() for p in text.split(" | ") if p.strip()]


def acct_name(w, aid) -> str:
    return (w.crm.account(aid) or {}).get("name", aid or "")


def order_lines(so: dict) -> str:
    if so["type"] == "Sample":
        return ", ".join(l["sku"] for l in so["lines"])
    if so["type"] == "CFA":
        return ", ".join(f"{l['sku']} cutting from {l['lot']}" for l in so["lines"])
    return "; ".join(f"{l['sku']} " + " + ".join(f"{a['yards']:g} yd from {a['lot']}" for a in l["allocation"])
                     for l in so["lines"])


def link(page: str, label: str, icon: str | None = None):
    if page in PAGES:
        st.page_link(PAGES[page], label=label, icon=icon)
