"""Perennials sample-to-quote demo.

    streamlit run demo/app.py      (from the repo root)

Pages share one in-memory workflow (seeded with the 27 workbook requests: 21 original + 6 added edge cases):
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

from demo.ui import common, compare, crm, erp, ops, website  # noqa: E402

st.set_page_config(page_title="Perennials Sample-to-Quote", page_icon="🧵", layout="wide")

common.PAGES.update({
    "website": st.Page(website.render, title="Website", icon="🛍", url_path="website"),
    "crm": st.Page(crm.render, title="CRM", icon="☁️", url_path="crm"),
    "erp": st.Page(erp.render, title="ERP", icon="🏭", url_path="erp"),
    "compare": st.Page(compare.render, title="Old vs New", icon="⚖️", url_path="compare"),
    "ops": st.Page(ops.render, title="Ops console", icon="🛠", url_path="ops"),
})
nav = st.navigation({"Systems": [common.PAGES[k] for k in ("website", "crm", "erp")],
                     "Story": [common.PAGES["compare"], common.PAGES["ops"]]})

with st.sidebar:
    with st.expander("Demo script", expanded=True):
        st.markdown(
            "1. **Website**: open *Tidal Herringbone*, Add Sample (Hospitality). Check out as **Dana Ruiz**.\n"
            "2. **CRM → Opportunities**: Ruiz Interiors. The new sample order is on her existing opportunity "
            "(no duplicate lead).\n"
            "3. **ERP → Sales orders**: the sample order, keyed to her CRM account.\n"
            "4. **CRM → Inbox**: send *Dana: 30 yds of the herringbone*. Quote priced, held, and sent with no one "
            "touching it.\n"
            "5. **ERP → Inventory**: herringbone lot L-2403 now shows 30 yd reserved.\n"
            "6. **Old vs New**: Ruiz Interiors. Every automated step next to the manual one it replaces.\n"
            "7. **CRM → Tasks**: Hannah (EML-026) is a new sender. Click **Qualify** and her quote is priced.\n"
            "8. Try the edge cases: *the canvas* (sample history), *the linen* (one question), a 90 ft quote line "
            "with CFA requested on the website.")
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
    st.caption("All systems are in-memory mocks seeded from `demo/data/perennials_sample_data.xlsx`.")

nav.run()
