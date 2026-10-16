"""Perennials sample-to-quote demo.

    streamlit run app.py

Pages share one in-memory workflow (seeded with the 21 workbook requests):
  Website      mock storefront: browse, add samples / quote lines, check out
  CRM          Salesforce-style: quotes@ inbox, leads, opportunities, tasks
  ERP          NetSuite-style: inventory by dye lot, sales orders, customers
  Old vs New   one customer's journey, manual today vs automated
  Ops console  every request's full story, review queue, integration log
"""
from __future__ import annotations

import streamlit as st

from ui import common, compare, crm, erp, ops, website

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
            "7. Try the edge cases: *the canvas* (sample history), *the linen* (one question), a 90 ft quote line "
            "with CFA requested on the website.")
    mode = st.radio("How emails are read", ["auto", "rules"], horizontal=True,
                    help="auto = Claude reads the email (rules run as a cross-check) when ANTHROPIC_API_KEY is set. "
                         "Website carts are structured, so they are never sent to the LLM.")
    if mode != st.session_state.get("mode", "auto"):
        st.session_state.mode = mode
        common.reset()
    st.caption(f"Email reader: **{common.wf().extractor.status}**")
    if st.button("↺ Reset demo", width="stretch"):
        common.reset()
        st.rerun()
    st.caption("All systems are in-memory mocks seeded from `data/perennials_sample_data.xlsx`.")

nav.run()
