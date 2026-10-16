"""Salesforce-style CRM mock: home, the shared quotes@ inbox, leads, accounts, opportunity
record pages, and the review task queue."""
from __future__ import annotations

import streamlit as st

from s2q import baseline, site

from .common import (acct_name, link, md, money, open_reviews, order_lines, reasons, review_buttons, system_header,
                     table, wf)
from .ops import quote_lines

# Ready-made emails for the demo: a clean one, a tricky one, and replays of the workbook's emails.
PRESETS = {
    "Dana: 30 yds of the herringbone (clean, auto-sent)":
        ("Dana Ruiz", "Ruiz Interiors", "dana@ruizinteriors.example",
         "Client loved the herringbone sample. Can you quote 30 yds of the herringbone and hold it?"),
    "Priya: 40 yds of 'the canvas' (color settled by her sample history)":
        ("Priya Natarajan", "Coastal Hospitality Group", "priya@coastalhg.example",
         "Need 40 yds of the canvas for the cabanas please."),
    "Mara: 10 yds of 'the linen' (real tie: drafts one question)":
        ("Mara Lowe", "Mara Lowe Design", "mara@maralowedesign.example", "Can I get 10 yds of the linen?"),
    "Write your own": ("", "", "", ""),
}


def inbox(w):
    st.markdown("#### quotes@ shared inbox")
    st.caption("Emails to the shared quote inbox are forwarded here (Gmail / Graph API push), read by Claude or the "
               "rules, and turned into a Quote on the right Opportunity. No one retypes them.")
    with st.container(border=True):
        st.markdown("**New email** (demo: play the customer)")
        preset = st.selectbox("Template", list(PRESETS) + [f"Replay {r['id']}: {r['name']}" for r in w.inbox
                                                           if r["channel"] == "Email" and int(r["id"][4:]) < 100])
        if preset.startswith("Replay"):
            r = next(x for x in w.inbox if x["id"] == preset.split()[1].rstrip(":"))
            name0, company0, email0, msg0 = r["name"], r["company"], r["email"], r["message"]
        else:
            name0, company0, email0, msg0 = PRESETS[preset]
        with st.form("email", border=False):
            a, b, c = st.columns(3)
            name = a.text_input("From name", value=name0)
            company = b.text_input("Company", value=company0)
            email = c.text_input("From email", value=email0)
            msg = st.text_area("Message", value=msg0, height=90)
            if st.form_submit_button("Send to quotes@", type="primary"):
                if "@" not in email or not msg.strip():
                    st.error("A sender email and a message are required.")
                else:
                    st.session_state.last_email = site.submit_email(w, name, company, email, msg)["request"]["id"]
                    st.rerun()
    if rid := st.session_state.get("last_email"):
        res = w.results[rid]
        st.success(md(f"**{rid}** read by **{res['extraction']['method']}** → {res['outcome']}"))
        if res.get("quote_id"):
            quote_lines(next(q for q in w.crm.quotes if q["id"] == res["quote_id"]))
        if res["email"]:
            with st.expander(f"Reply drafted: {res['email']['subject']}", expanded=True):
                st.code(res["email"]["body"], language=None, wrap_lines=True)
    st.markdown("**Received**")
    mails = sorted((r for r in w.inbox if r["channel"] == "Email"), key=lambda r: r["received"], reverse=True)
    table(mails, {"ID": "id", "Received": lambda r: f"{r['received']:%b %d %H:%M}", "From": "name",
                  "Message": "message", "Result": lambda r: w.results[r["id"]]["outcome"] if r["id"] in w.results else ""})


def opportunity(w):
    opps = sorted(w.crm.opportunities, key=lambda o: o["created"], reverse=True)
    oid = st.selectbox("Opportunity", [o["id"] for o in opps],
                       format_func=lambda i: next(f"{o['id']} · {o['name']}" for o in opps if o["id"] == i))
    o = next(x for x in opps if x["id"] == oid)
    contact = next((c for c in w.crm.contacts if c["id"] == o["contact_id"]), {})
    st.markdown(f"### {o['name']}")
    f = st.columns(4)
    f[0].markdown(f"**Account**  \n{acct_name(w, o['account_id'])}")
    f[1].markdown(f"**Contact**  \n{contact.get('name', '')}")
    f[2].markdown(f"**Stage**  \n{o['stage']}")
    f[3].markdown(md(f"**Amount**  \n{money(o['amount'])}"))

    st.markdown("**Sample orders** (from the ERP)")
    table([s for s in w.erp.sales_orders if s["id"] in o["sample_orders"]],
          {"Order": "id", "Status": "status", "Samples": order_lines, "Created": lambda s: f"{s['created']:%b %d}"})
    st.markdown("**Quotes**")
    quotes = [q for q in w.crm.quotes if q["opp_id"] == oid]
    table(quotes, {"Quote": "id", "Status": "status", "Total": "total",
                   "Valid until": lambda q: f"{q['valid_until']:%b %d}", "ERP hold": "reservation_id",
                   "CFA": lambda q: q.get("cfa_order_id") or ""}, money_cols=["Total"])
    for q in reversed(quotes):
        with st.expander(f"{q['id']} lines" + (f" · {len(q['flags'])} flag(s)" if q["flags"] else "")):
            quote_lines(q)
            for fl in q["flags"]:
                st.caption(md(f"⚠ {fl}"))
    rids = baseline.journeys(w).get(o["account_id"], [])
    st.markdown("**Activity** (every request on this account)")
    table([w.results[r] for r in rids], {"Request": lambda r: r["request"]["id"], "Type": lambda r: r["request"]["type"],
                                         "Received": lambda r: f"{r['request']['received']:%b %d %H:%M}",
                                         "Outcome": "outcome"})


def tasks(w):
    todo = open_reviews(w)
    st.caption("Review items become Tasks assigned to the rep's queue. Approving runs the waiting action.")
    if not todo:
        st.success("No open tasks.")
    for rv in todo:
        req = w.results[rv["request"]]["request"]
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**{rv['request']} · {req['name'] or req['email']}**: {rv['stage']}")
                st.markdown("\n".join(f"- {md(r)}" for r in reasons(rv)))
                st.caption(md(f"Proposed: {rv['proposed']} · {rv['task_id']} · owner: {rv['owner']}"))
            with c2:
                review_buttons(w, rv, "crm")


def render():
    w = wf()
    system_header("crm", "CRM", "Salesforce-style mock · people, opportunities, quotes, tasks")
    t = st.tabs(["Home", "Inbox (quotes@)", "Leads", "Accounts & contacts", "Opportunities",
                 f"Tasks ({len(open_reviews(w))})"])
    with t[0]:
        m = st.columns(4)
        m[0].metric("Leads", len(w.crm.leads))
        m[1].metric("Open opportunities", sum(1 for o in w.crm.opportunities if not o["stage"].startswith("Closed")))
        m[2].metric("Quotes sent", sum(1 for q in w.crm.quotes if q["status"] == "Sent"))
        m[3].metric("Open tasks", len(open_reviews(w)))
        st.markdown("**Recent activity** (written by the integration, not typed by a person)")
        table(list(reversed([e for e in w.log.events if e["system"] == "CRM"]))[:12],
              {"Time": "sim_time", "Request": "request", "Action": "action", "Detail": "detail"})
        link("website", "Place a new order on the website", "🛍")
    with t[1]:
        inbox(w)
    with t[2]:
        table(list(reversed(w.crm.leads)), {"ID": "id", "Name": "name", "Company": "company", "Email": "email",
                                            "Source": "source", "Status": "status", "Why": "status_reason"})
    with t[3]:
        table(w.crm.accounts, {"ID": "id", "Name": "name", "Type": "type", "Status": "status"})
        table(w.crm.contacts, {"ID": "id", "Name": "name", "Account": lambda c: acct_name(w, c["account_id"]),
                               "Email": "email", "Other emails": lambda c: ", ".join(c.get("alt_emails", []))})
    with t[4]:
        opportunity(w)
    with t[5]:
        tasks(w)
