"""Perennials sample-to-quote demo.

    streamlit run demo/app.py      (from the repo root)

Pages share one in-memory workflow. It starts clean (inventory, prices and existing accounts only), or with
the 27 workbook requests processed when "Start from" is set to the history:
  Today        the old process by hand: blank Gmail, Salesforce and NetSuite, measured live (own state)
  Website      mock storefront: browse, add samples / quote lines, check out
  CRM          Salesforce-style: quotes@perennialsfabrics.com inbox, leads, opportunities, tasks
  ERP          NetSuite-style: inventory by dye lot, sales orders, customers
  Old vs New   one customer's journey, manual today vs automated
  Ops console  every request's full story, review queue, integration log
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, so `s2q` and `demo` import

from demo.ui import common, compare, crm, erp, manual, ops, website  # noqa: E402

st.set_page_config(page_title="Perennials Sample-to-Quote", page_icon=":material/texture:", layout="wide")

common.PAGES.update({
    "website": st.Page(website.render, title="Website", icon=":material/storefront:", url_path="website"),
    "crm": st.Page(crm.render, title="CRM", icon=":material/contacts:", url_path="crm"),
    "erp": st.Page(erp.render, title="ERP", icon=":material/inventory_2:", url_path="erp"),
    "manual": st.Page(manual.render, title="Today (manual)", icon=":material/edit_note:", url_path="manual"),
    "compare": st.Page(compare.render, title="Old vs New", icon=":material/compare_arrows:", url_path="compare"),
    "ops": st.Page(ops.render, title="Ops console", icon=":material/build:", url_path="ops"),
})
nav = st.navigation({"New system": [common.PAGES[k] for k in ("website", "crm", "erp")],
                     "Today": [common.PAGES["manual"]],
                     "Story": [common.PAGES["compare"], common.PAGES["ops"]]})

with st.sidebar:
    with st.expander("Demo script (new system)", expanded=True):
        st.markdown(
            "1. **Website**: add samples of *Tidal Herringbone* and *Canvas Solid* White. Check out as "
            "**Dana Ruiz**, a new customer.\n"
            "2. **CRM → Tasks**: one **Qualify**. Lead converted, opportunity created, sample order in the ERP, "
            "confirmation drafted.\n"
            "3. **Website**: Request A Quote, 30 yd of the herringbone, CFA requested. Priced, held and sent.\n"
            "4. **CRM → Inbox**: send *Dana: bump the herringbone to 45 yds*. Claude reads it; the quote is "
            "revised, re-held and sent.\n"
            "5. **ERP**: lot L-2403 shows 45 yd reserved; sample, hold and CFA orders.\n"
            "6. **Old vs New**: measured against the **Today (manual)** run.")
    start = st.radio("Start from", ["clean", "history"], horizontal=True,
                     format_func={"clean": "Day one", "history": "Workbook history"}.get,
                     help="Day one: NetSuite inventory and prices and the existing Salesforce accounts, nothing "
                          "processed. Workbook history: the 27 workbook requests already processed, for Q&A and edge cases.")
    if start != st.session_state.get("start", "clean"):
        st.session_state.start = start
        common.reset()
    mode = st.radio("How emails are read", ["auto", "rules"], horizontal=True,
                    help="auto = Claude reads the email (rules run as a cross-check) when ANTHROPIC_API_KEY is set. "
                         "Website carts are structured, so they are never sent to the LLM.")
    if mode != st.session_state.get("mode", "auto"):
        st.session_state.mode = mode
        common.reset()
    ex = common.wf().extractor
    st.caption(f"Email reader: **{ex.status}**")
    if ex.failures:
        st.warning(f"{ex.failures} Claude call(s) failed and fell back to rules. See the Ops console's raw data.")
    if st.button("↺ Reset demo", width="stretch"):
        common.reset()
        st.rerun()
    st.caption("All systems are in-memory mocks loaded from `demo/data/perennials_sample_data.xlsx`.")

nav.run()
