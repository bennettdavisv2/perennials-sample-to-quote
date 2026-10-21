"""Today (manual): the old process, filmed. You play Dana on the website and in her inbox, and the CSR in a
blank Gmail, Salesforce and NetSuite. Nothing is connected: every value is typed and every email written by
hand. The scoreboard measures it live (demo/manual.py)."""
from __future__ import annotations

import streamlit as st

from demo import manual
from demo.manual import ORDERS, QUOTES, Desk

from .common import md, money, system_header, table

DANA = ("Dana Ruiz", "Ruiz Interiors", "dana@ruizinteriors.example")
CHANGE_EMAIL = ("Re: your quote", "Client signed off on the herringbone. Can you bump it to 45 yds and add 20 yds "
                                  "of the canvas for the cushions?")


@st.cache_resource
def shared() -> dict:
    """The latest manual run's numbers, readable from any browser window (the Old vs New page shows them)."""
    return {}


def desk() -> Desk:
    if "desk" not in st.session_state:
        st.session_state.desk = Desk.new()
    return st.session_state.desk


def reset():
    st.session_state.pop("desk", None)
    shared().clear()


def _publish(d: Desk):
    shared().update(d.summary(), checklist=d.checklist(), quote_checks=[d.check_quote(q) for q in d.quotes])


@st.fragment(run_every="1s")
def scoreboard():
    d = desk()
    s = d.summary()
    m = st.columns(5)
    mins, secs = divmod(int(s["elapsed_s"]), 60)
    m[0].metric("Elapsed", f"{mins}:{secs:02d}", help="From the CSR's first action. Stop the clock when you're done.")
    m[1].metric("Values typed by hand", s["typed"])
    m[2].metric("Emails written", s["emails"])
    m[3].metric("System switches", s["switches"])
    m[4].metric("Steps done", f"{s['steps_done']}/{sum(1 for _, x, _ in d.checklist() if '(customer)' not in x)}")


def checklist(d: Desk):
    st.markdown("**Today's process**")
    section = None
    for sec, step, done in d.checklist():
        if sec != section:
            st.caption(sec)
            section = sec
        st.markdown(f"{'~~' if done else ''}{'☑' if done else '☐'} {step}{'~~' if done else ''}")


def _skus(d: Desk) -> list[str]:
    return sorted({l["sku"] for l in d.lots})


# ---------------------------------------------------------------------- Dana (customer)
def customer(d: Desk):
    st.caption("You're Dana. What she types isn't counted: customers type the same in both worlds.")
    web, mail = st.tabs(["Website", "Dana's inbox"])
    with web:
        a, b = st.columns(2, gap="large")
        with a, st.form("m-sample"):
            st.markdown("**Add samples and check out**")
            skus = st.multiselect("Samples", _skus(d), default=["PF-1008", "PF-1010"], format_func=d.item_label)
            ptype = st.radio("Project Type", ["Hospitality", "Residential"], horizontal=True)
            pname = st.text_input("Project name", "Hotel lobby, Malibu")
            note = st.text_area("Order notes", "Lobby banquettes for a boutique hotel.", height=68)
            if st.form_submit_button("Place order", type="primary"):
                d.web_sample_request(*DANA, skus, ptype, pname, note)
                st.toast("Order placed. The website emails a notification to quotes@")
        with b, st.form("m-quote"):
            st.markdown("**Request A Quote**")
            sku = st.selectbox("Fabric", _skus(d), index=_skus(d).index("PF-1008"), format_func=d.item_label)
            c1, c2 = st.columns([2, 1])
            length = c1.number_input("Length", min_value=0.0, value=30.0, step=1.0)
            unit = c2.selectbox("Unit", ["Yards", "Feet", "Meters"])
            cfa = st.radio("CFA", ["CFA Requested", "CFA Waived"], horizontal=True)
            qname = st.text_input("Project Name *", "Hotel lobby, Malibu")
            if st.form_submit_button("Submit quote request", type="primary"):
                d.web_quote_request(*DANA, sku, length, unit, cfa, qname)
                st.toast("Quote request sent. The website emails a notification to quotes@")
    with mail:
        _mail_list(d, DANA[2], "dana")
        with st.form("m-dana-mail"):
            st.markdown(f"**New email to {QUOTES}**")
            subj = st.text_input("Subject", CHANGE_EMAIL[0])
            body = st.text_area("Message", CHANGE_EMAIL[1], height=80)
            if st.form_submit_button("Send", type="primary"):
                d.customer_email(DANA[2], subj, body)
                st.toast("Sent to quotes@")


# ---------------------------------------------------------------------- CSR: Gmail
def _mail_list(d: Desk, address: str, key: str):
    box = d.mailbox(address)
    i = table(box, {"From": "from", "To": "to", "Subject": "subject"}, key=f"mail-{key}", select=True)
    if i is not None:
        m = box[i]
        st.code(f"From: {m['from']}\nTo: {m['to']}\nSubject: {m['subject']}\n\n{m['body']}", language=None,
                wrap_lines=True)
    elif box:
        st.caption("Click a message to open it.")


def gmail(d: Desk):
    who = st.radio("Mailbox", [QUOTES, ORDERS], horizontal=True,
                   format_func=lambda a: f"{a} ({'CSR' if a == QUOTES else 'order ops'})")
    _mail_list(d, who, who)
    with st.form("m-compose", clear_on_submit=True):
        st.markdown("**Compose**")
        c1, c2 = st.columns(2)
        frm = c1.selectbox("From", [QUOTES, ORDERS], index=0 if who == QUOTES else 1)
        to = c2.text_input("To")
        subj = st.text_input("Subject")
        body = st.text_area("Message", height=140)
        if st.form_submit_button("Send", type="primary"):
            if "@" not in to or not body.strip():
                st.error("A recipient and a message are required.")
            else:
                d.send(frm, to, subj, body)
                st.toast(f"Sent to {to}")


# ---------------------------------------------------------------------- CSR: Salesforce
def salesforce(d: Desk):
    view = st.radio("Salesforce", ["Search", "Leads", "Convert lead", "Opportunities", "Quotes",
                                   "Accounts & contacts"], horizontal=True, label_visibility="collapsed")
    if view == "Search":
        with st.form("m-search"):
            q = st.text_input("Search Salesforce", placeholder="name, company or email")
            if st.form_submit_button("Search"):
                st.session_state.m_hits = d.search(q)
        hits = st.session_state.get("m_hits")
        if hits is not None:
            table(hits, {"Type": "type", "ID": "id", "Name": "name", "Detail": "detail"}) if hits else \
                st.info("No matches.")
    elif view == "Leads":
        table(d.leads, {"ID": "id", "Name": "name", "Company": "company", "Email": "email", "Status": "status"})
        with st.form("m-lead", clear_on_submit=True):
            st.markdown("**New lead**")
            a, b, c = st.columns(3)
            name, company, email = a.text_input("Name"), b.text_input("Company"), c.text_input("Email")
            a, b, c = st.columns(3)
            source = a.selectbox("Lead source", ["", "Web sample request", "Web quote request", "Email", "Phone"])
            status = b.selectbox("Status", ["", "New", "Working", "Qualified", "Disqualified"])
            project = c.text_input("Project")
            desc = st.text_area("Description", height=68)
            if st.form_submit_button("Save", type="primary"):
                d.create_lead(name, company, email, source, project, desc, status)
                st.toast("Lead saved")
    elif view == "Convert lead":
        open_leads = [l for l in d.leads if l["status"] != "Converted"]
        if not open_leads:
            st.info("No leads to convert. Create one under Leads first.")
            return
        lid = st.selectbox("Lead", [l["id"] for l in open_leads],
                           format_func=lambda i: next(f"{l['id']} · {l['name']}" for l in open_leads if l["id"] == i))
        lead = next(l for l in open_leads if l["id"] == lid)
        with st.form("m-convert"):
            st.caption("Salesforce copies the lead's fields into the new records; check each and fix what's wrong.")
            a, b = st.columns(2)
            acct = a.text_input("Account name", lead["company"])
            atype = b.selectbox("Account type", ["", "Trade – Interior Designer", "Trade – Hospitality",
                                                 "Trade – Architect", "Trade – Upholsterer", "Trade – Marine"])
            cname, cemail = a.text_input("Contact name", lead["name"]), b.text_input("Contact email", lead["email"])
            if st.form_submit_button("Convert", type="primary"):
                d.type(-sum(1 for x, y in ((acct, lead["company"]), (cname, lead["name"]), (cemail, lead["email"]))
                            if x == y))  # copied by Salesforce, not typed
                d.convert_lead(lid, acct, atype, cname, cemail)
                st.toast("Converted: account and contact created")
    elif view == "Opportunities":
        table(d.opportunities, {"ID": "id", "Name": "name", "Account": "account_id", "Stage": "stage",
                                "Amount": "amount"}, money_cols=["Amount"])
        with st.form("m-opp", clear_on_submit=True):
            st.markdown("**New opportunity**")
            a, b = st.columns(2)
            name = a.text_input("Opportunity name")
            acct = b.selectbox("Account", [""] + [x["id"] for x in d.accounts],
                               format_func=lambda i: next((f"{x['id']} · {x['name']}" for x in d.accounts
                                                           if x["id"] == i), ""))
            contact = a.selectbox("Contact", [""] + [x["id"] for x in d.contacts],
                                  format_func=lambda i: next((f"{x['id']} · {x['name']}" for x in d.contacts
                                                              if x["id"] == i), ""))
            stage = b.selectbox("Stage", ["", "Sampling", "Quoting", "Quote Sent"])
            close = a.date_input("Close date", value=None)
            amount = b.number_input("Amount", min_value=0.0, step=100.0)
            if st.form_submit_button("Save", type="primary"):
                d.create_opportunity(name, acct, contact, stage, close, amount)
                st.toast("Opportunity saved")
    elif view == "Quotes":
        for q in d.quotes:
            chk = d.check_quote(q)
            st.markdown(md(f"**{q['id']}** · {q['opp_id']} · {money(q['total'])} · {q['status']}"))
            for p in chk["problems"]:
                st.caption(md(f"Pricing check: {p}"))
        if not d.opportunities:
            st.info("Create an opportunity first.")
            return
        with st.form("m-quote-sf", clear_on_submit=True):
            st.markdown("**New quote** (type each line from NetSuite and work out the trade price yourself)")
            opp = st.selectbox("Opportunity", [o["id"] for o in d.opportunities],
                               format_func=lambda i: next(f"{o['id']} · {o['name']}" for o in d.opportunities
                                                          if o["id"] == i))
            lines = []
            for n in range(3):
                c = st.columns([1.2, 2, 1, 1, 1.2])
                vis = "visible" if n == 0 else "collapsed"  # labels on the first row only
                lines.append({"sku": c[0].text_input("SKU", key=f"ql-s{n}", label_visibility=vis),
                              "description": c[1].text_input("Description", key=f"ql-d{n}", label_visibility=vis),
                              "yards": c[2].number_input("Yards", min_value=0.0, step=1.0, key=f"ql-y{n}",
                                                         label_visibility=vis),
                              "unit_price": c[3].number_input("$/yd", min_value=0.0, step=0.01, key=f"ql-p{n}",
                                                              label_visibility=vis),
                              "line_total": c[4].number_input("Line total", min_value=0.0, step=0.01, key=f"ql-t{n}",
                                                              label_visibility=vis)})
            a, b = st.columns(2)
            total = a.number_input("Quote total", min_value=0.0, step=0.01)
            valid = b.date_input("Valid until", value=None)
            if st.form_submit_button("Save quote", type="primary"):
                d.create_quote(opp, lines, total, valid)
                st.toast("Quote saved. Now export the PDF and email it to Dana.")
    else:
        table(d.accounts, {"ID": "id", "Name": "name", "Type": "type", "Status": "status"})
        table(d.contacts, {"ID": "id", "Name": "name", "Account": "account_id", "Email": "email"})


# ---------------------------------------------------------------------- CSR: NetSuite
def netsuite(d: Desk):
    view = st.radio("NetSuite", ["Inventory", "Customers", "Sales orders"], horizontal=True,
                    label_visibility="collapsed")
    if view == "Inventory":
        with st.form("m-lookup"):
            q = st.text_input("Item search", placeholder="SKU, fabric or color")
            if st.form_submit_button("Search"):
                st.session_state.m_lots = d.lookup(q)
        lots = st.session_state.get("m_lots")
        if lots is not None:
            table(lots, {"SKU": "sku", "Fabric": "fabric", "Color": "color", "Status": "status", "Dye lot": "lot",
                         "On hand": "on_hand", "Reserved": "reserved",
                         "Available": lambda l: l["on_hand"] - l["reserved"], "List $/yd": "list_price"},
                      money_cols=["List $/yd"]) if lots else st.info("No items found.")
        c = d.pricing
        tiers = ", ".join(f"+{p * 100:.0f}% at {y}+ yd" for y, p in sorted(c.volume_tiers))
        st.caption(md(f"Price sheet (pinned PDF on the shared drive): trade {c.trade_discount * 100:.0f}% off list; "
                      f"volume {tiers} (trade only, added to the trade discount); ${c.cut_fee:.0f} cut fee under "
                      f"{c.cut_fee_under_yards:g} yd; quotes valid {c.quote_valid_days} days; "
                      f"holds {c.hold_days} days."))
    elif view == "Customers":
        table(d.customers, {"ID": "id", "Name": "name", "Email": "email", "Salesforce account": "sf_account",
                            "Price level": "price_level"})
        with st.form("m-cust", clear_on_submit=True):
            st.markdown("**New customer**")
            a, b = st.columns(2)
            name, email = a.text_input("Company name"), b.text_input("Email")
            sf = a.text_input("Salesforce account ID", placeholder="copy it from Salesforce")
            level = b.selectbox("Price level", ["", "Trade", "Retail"])
            terms = a.selectbox("Terms", ["", "Prepaid", "Net 30"])
            if st.form_submit_button("Save", type="primary"):
                d.create_customer(name, email, sf, level, terms)
                st.toast("Customer saved")
    else:
        table(d.orders, {"Order": "id", "Form": "form", "Customer": "customer", "Status": "status",
                         "Lines": lambda o: "; ".join(f"{l['sku']} {l.get('lot') or ''} x{l['qty']:g}"
                                                      for l in o["lines"]),
                         "Memo": "memo"})
        holds = [o for o in d.orders if o["form"] == "Pending hold" and o["status"] != "Released"]
        if holds:
            c1, c2 = st.columns([3, 1])
            so = c1.selectbox("Release a hold", [o["id"] for o in holds])
            if c2.button("Release", width="stretch"):
                d.release(so)
                st.rerun()
        with st.form("m-so", clear_on_submit=True):
            st.markdown("**New sales order**")
            a, b = st.columns(2)
            form = a.selectbox("Custom form", ["", "Sample", "Pending hold"])
            cust = b.selectbox("Customer", [""] + [c["id"] for c in d.customers],
                               format_func=lambda i: next((f"{c['id']} · {c['name']}" for c in d.customers
                                                           if c["id"] == i), ""))
            lines = []
            for n in range(3):
                c = st.columns(3)
                vis = "visible" if n == 0 else "collapsed"
                lines.append({"sku": c[0].text_input("SKU", key=f"so-s{n}", label_visibility=vis),
                              "lot": c[1].text_input("Dye lot (holds only)", key=f"so-l{n}", label_visibility=vis),
                              "qty": c[2].number_input("Qty (swatches or yards)", min_value=0.0, step=1.0,
                                                       key=f"so-q{n}", label_visibility=vis)})
            a, b = st.columns(2)
            ship = a.text_input("Ship to")
            memo = b.text_input("Memo", placeholder="e.g. quote number")
            if st.form_submit_button("Save order", type="primary"):
                if not form or not cust:
                    st.error("Pick a form and a customer.")
                else:
                    so, errors = d.create_order(form, cust, memo, lines, ship)
                    for e in errors:
                        st.error(e)
                    if so:
                        st.toast(f"{so['id']} saved")


# ---------------------------------------------------------------------- page
def render():
    d = desk()
    system_header("manual", "TODAY (MANUAL)", "no integration: a blank Gmail, Salesforce and NetSuite, all by hand")
    scoreboard()
    main, side = st.columns([3, 1], gap="large")
    with side:
        checklist(d)
        if st.button("Stop the clock", width="stretch", disabled=d.stopped is not None or d.started is None):
            d.stop()
            st.rerun()
        if st.button("Reset manual run", width="stretch"):
            reset()
            st.rerun()
    with main:
        role = st.segmented_control("You are", ["Dana (customer)", "CSR"], default="Dana (customer)",
                                    key="m_role") or "Dana (customer)"
        if role.startswith("Dana"):
            customer(d)
        else:
            system = st.segmented_control("System", list(manual.CSR_SYSTEMS), default=d.system, key="m_system") \
                or d.system
            d.switch(system)
            {"Gmail": gmail, "Salesforce": salesforce, "NetSuite": netsuite}[system](d)
    _publish(d)
