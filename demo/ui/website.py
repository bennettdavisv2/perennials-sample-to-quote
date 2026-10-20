"""Mock storefront. Models the real site's flow and form fields (not its branding):
product page -> Add Sample (colorway + Project Type) or Request A Quote (Length + unit, Date
Needed, CFA, Project Name/Type, Comment) -> cart -> guest checkout. Checkout runs the workflow."""
from __future__ import annotations

import streamlit as st

from demo import site

from .common import link, md, swatch, system_header, wf

PERSONAS = {
    "Dana Ruiz · Ruiz Interiors": ("Dana Ruiz", "Ruiz Interiors", "dana@ruizinteriors.example", ""),
    "Alex Rivera · new designer, business email": ("Alex Rivera", "Rivera Design Studio", "alex@riveradesign.example",
                                                   ""),
    "Chris Lee · homeowner, personal email": ("Chris Lee", "", "chris.lee@gmail.example",
                                              "Redoing the cushions on my patio furniture."),
    "Blank": ("", "", "", ""),
}


def go(view: str, fabric: str | None = None):
    st.session_state.site_view = view
    if fabric:
        st.session_state.site_fabric = fabric
    st.rerun()


def cart() -> list[dict]:
    return st.session_state.setdefault("cart", [])


def grid(products):
    st.markdown("### Performance fabrics")
    st.caption("Log in to see pricing and availability.")
    for row in range(0, len(products), 4):
        for col, p in zip(st.columns(4), products[row:row + 4]):
            with col.container(border=True):
                st.markdown("".join(swatch(site.SWATCH.get(c["color"], "#ccc"), 34, c["color"])
                                    for c in p["colorways"]), unsafe_allow_html=True)
                st.markdown(f"**{p['fabric']}**")
                status = {c["status"] for c in p["colorways"]} - {"Active"}
                st.caption(f"{len(p['colorways'])} colorway{'s' * (len(p['colorways']) > 1)}"
                           + (f" · {', '.join(status)}" if status else ""))
                if st.button("View", key=f"view-{p['fabric']}", width="stretch"):
                    go("product", p["fabric"])


def product(products):
    p = next(x for x in products if x["fabric"] == st.session_state.get("site_fabric"))
    if st.button("← All fabrics"):
        go("grid")
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown(f"## {p['fabric']}")
        names = [c["color"] for c in p["colorways"]]
        color = st.radio("Colorway", names, horizontal=True, key=f"color-{p['fabric']}")
        item = next(c for c in p["colorways"] if c["color"] == color)
        st.markdown(swatch(site.SWATCH.get(color, "#ccc"), 220), unsafe_allow_html=True)
        st.caption(f"SKU {item['sku']} · {item['status']}")
        st.caption("Log in to see pricing and availability.")
    with right:
        with st.container(border=True):
            st.markdown("**Add Sample**")
            if item["status"] == "Discontinued":
                st.caption("Discontinued: samples are no longer available.")
            else:
                ptype = st.radio("Project Type", ["Residential", "Hospitality"], horizontal=True, key="s-ptype")
                if st.button("Add Sample To Cart", type="primary", width="stretch"):
                    cart().append({"kind": "sample", "sku": item["sku"], "label": f"{p['fabric']} · {color}",
                                   "project_type": ptype.lower()})
                    st.toast(f"Sample of {p['fabric']} {color} added to cart")
        with st.form("quote-form", border=True):
            st.markdown("**Request A Quote**")
            st.caption("A Perennials team member will review your request. Submission does not indicate purchase.")
            a, b = st.columns([2, 1])
            length = a.number_input("Length", min_value=0.0, step=1.0, value=0.0)
            unit = b.selectbox("Unit", ["Yards", "Feet", "Meters"])
            need = st.date_input("Date Needed", value=None)
            cfa = st.radio("CFA (cutting for approval)", ["CFA Waived", "CFA Requested"], horizontal=True)
            pname = st.text_input("Project Name *")
            qptype = st.radio("Project *", ["Residential", "Hospitality"], horizontal=True)
            comment = st.text_area("Comment/Sidemark", height=68)
            if st.form_submit_button("Add to Cart", width="stretch"):
                if length <= 0 or not pname.strip():
                    st.error("Length and Project Name are required.")
                else:
                    cart().append({"kind": "quote", "sku": item["sku"], "label": f"{p['fabric']} · {color}",
                                   "length": length, "unit": unit, "date_needed": need.isoformat() if need else None,
                                   "cfa": "requested" if cfa == "CFA Requested" else "waived",
                                   "project_name": pname.strip(), "project_type": qptype.lower(), "comment": comment})
                    st.toast(f"Quote request for {length:g} {unit.lower()} added to cart")


def cart_view():
    st.markdown("### Cart")
    items = cart()
    if not items:
        st.info("Your cart is empty.")
        if st.button("Browse fabrics"):
            go("grid")
        return
    for i, it in enumerate(items):
        c1, c2 = st.columns([5, 1])
        if it["kind"] == "sample":
            c1.markdown(f"**Sample** · {it['label']} ({it['sku']}) · {it['project_type'].title()}")
        else:
            c1.markdown(md(f"**Quote request** · {it['label']} ({it['sku']}) · {it['length']:g} {it['unit']} · "
                           f"{'CFA requested' if it['cfa'] == 'requested' else 'CFA waived'} · project "
                           f"'{it['project_name']}'" + (f" · needed {it['date_needed']}" if it["date_needed"] else "")))
        if c2.button("Remove", key=f"rm-{i}"):
            items.pop(i)
            st.rerun()
    if st.button("Proceed to checkout", type="primary"):
        go("checkout")


def checkout():
    st.markdown("### Checkout")
    persona = st.selectbox("Demo: fill in as", list(PERSONAS))
    name0, company0, email0, note0 = PERSONAS[persona]
    with st.form("checkout"):
        a, b = st.columns(2)
        name = a.text_input("Full name *", value=name0)
        company = b.text_input("Company", value=company0)
        email = a.text_input("Email *", value=email0)
        b.text_input("Ship-to city / state", value="", help="Not used by the demo (shipping is out of scope)")
        project = st.text_input("Project name", value="")
        note = st.text_area("Order notes (optional)", value=note0, height=80)
        if st.form_submit_button("Place order", type="primary"):
            if not name.strip() or "@" not in email:
                st.error("Name and a valid email are required.")
                return
            items = cart()
            samples = [{"sku": i["sku"], "project_type": i["project_type"]} for i in items if i["kind"] == "sample"]
            quotes = [{k: i[k] for k in ("sku", "length", "unit", "date_needed", "cfa", "project_type", "project_name")}
                      for i in items if i["kind"] == "quote"]
            notes = " ".join(x for x in [note.strip()] + [i["comment"] for i in items if i.get("comment")] if x)
            results = site.submit_checkout(wf(), {"name": name.strip(), "company": company.strip(), "email": email},
                                           samples, quotes, project_name=project.strip(), note=notes)
            st.session_state.last_order = [r["request"]["id"] for r in results]
            st.session_state.cart = []
            go("thanks")


def thanks():
    w = wf()
    ids = st.session_state.get("last_order", [])
    st.markdown("### Thank you, your order was received")
    st.caption("This is all the customer sees. Everything below happened automatically, with no one retyping anything.")
    for rid in ids:
        res = w.results[rid]
        with st.container(border=True):
            took = f" · in {res['elapsed_s']:.1f} s" if "elapsed_s" in res else ""
            st.markdown(f"**{rid}** · {res['request']['type']} → **{md(res['outcome'])}**{took}")
            for n, s in sorted(res["stages"].items()):
                if s["status"] != "n/a" and s["summary"]:
                    st.caption(md(f"{n}. {s['stage']}: {s['summary']}"))
            if res["email"]:
                with st.expander(f"Email to the customer: {res['email']['subject']}"):
                    st.code(res["email"]["body"], language=None, wrap_lines=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        link("crm", "See it in the CRM", ":material/contacts:")
    with c2:
        link("erp", "See it in the ERP", ":material/inventory_2:")
    with c3:
        link("compare", "Compare with today's process", ":material/compare_arrows:")
    if st.button("Continue shopping"):
        go("grid")


def render():
    w = wf()
    products = site.fabrics(w.erp.items())
    system_header("site", "PERENNIALS", "Demo storefront · a mock modelled on the real site's sample and quote flow")
    view = st.session_state.get("site_view", "grid")
    _, c2, c3 = st.columns([6, 1, 1])
    if c2.button("Fabrics", width="stretch"):
        go("grid")
    if c3.button(f"Cart ({len(cart())})", width="stretch", type="primary" if cart() else "secondary"):
        go("cart")
    {"grid": lambda: grid(products), "product": lambda: product(products), "cart": cart_view,
     "checkout": checkout, "thanks": thanks}[view]()
