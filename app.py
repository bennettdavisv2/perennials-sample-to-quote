"""Streamlit front end for the sample-to-quote PoC.

    streamlit run app.py
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from s2q.workflow import STAGES, Workflow

st.set_page_config(page_title="Perennials Sample-to-Quote", layout="wide")

BADGE = {"done": "✅", "review": "🟡", "blocked": "⛔", "skipped": "➖", "waiting": "⏳", "n/a": "·"}


def md(text: str) -> str:
    """Escape $ so Streamlit markdown doesn't render prices as LaTeX."""
    return str(text).replace("$", "\\$")


def wf() -> Workflow:
    if "wf" not in st.session_state:
        st.session_state.wf = Workflow(mode=st.session_state.get("mode", "auto"))
    return st.session_state.wf


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Sample-to-Quote PoC")
    mode = st.radio("Extraction", ["auto", "rules"], horizontal=True,
                    help="auto = Claude if ANTHROPIC_API_KEY is set (rules cross-check), else rules")
    if mode != st.session_state.get("mode", "auto"):
        st.session_state.mode = mode
        st.session_state.pop("wf", None)
    w = wf()
    st.caption(f"Extractor: {w.extractor.status}")
    c1, c2 = st.columns(2)
    if c1.button("▶ Next request", width="stretch", disabled=not w.pending()):
        r = w.process_next()
        st.session_state.selected = r["request"]["id"]
    if c2.button("⏭ Process all", width="stretch", disabled=not w.pending()):
        w.process_all()
    if st.button("↺ Reset", width="stretch"):
        st.session_state.pop("wf", None)
        st.rerun()
    st.divider()
    open_rv = sum(1 for r in w.reviews if r["status"] == "Open")
    st.metric("Processed", f"{len(w.results)} / {len(w.inbox)}")
    st.metric("Open reviews", open_rv)
    st.metric("Quotes sent", sum(1 for q in w.crm.quotes if q["status"] == "Sent"))
    st.caption("Systems are in-memory mocks seeded from data/perennials_sample_data.xlsx. "
               "Simulated time = each request's received timestamp.")

st.title("Perennials · Sample-to-Quote")
tab_inbox, tab_review, tab_crm, tab_erp, tab_log = st.tabs(
    ["📥 Inbox & pipeline", f"🧑‍💼 Review queue ({open_rv})", "📇 CRM", "🏭 ERP", "📜 Audit log"])

# ---------------------------------------------------------------- inbox
with tab_inbox:
    rows = []
    for r in w.inbox:
        res = w.results.get(r["id"])
        row = {"ID": r["id"], "Received": r["received"].strftime("%m-%d %H:%M"),
               "From": r["name"] or r["email"], "Company": r["company"] or ""}
        row["Pipeline 1-6"] = " ".join(BADGE.get(res["stages"].get(n, {}).get("status", ""), "") for n in STAGES) if res else ""
        row["Outcome"] = res["outcome"] if res else "pending"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=35 * (len(rows) + 1) + 3)
    st.caption("Stages: " + " · ".join(f"{n} {s}" for n, s in STAGES.items())
               + "   |   ✅ done 🟡 needs review ⛔ blocked ➖ skipped ⏳ waiting")

    done_ids = list(w.results)
    if done_ids:
        default = st.session_state.get("selected", done_ids[-1])
        sel = st.selectbox("Request detail", done_ids, index=done_ids.index(default) if default in done_ids else 0,
                           format_func=lambda i: f"{i} · {w.results[i]['request']['name'] or w.results[i]['request']['email']} · {w.results[i]['outcome']}")
        res = w.results[sel]
        req = res["request"]
        left, right = st.columns([1, 1])
        with left:
            st.markdown(f"**{req['type']}** via {req['channel']} · {req['received']:%Y-%m-%d %H:%M} UTC")
            st.markdown(f"**{req['name'] or '(no name)'}** · {req['company'] or '(no company)'} · `{req['email']}`")
            st.info(req["message"])
            st.markdown("##### Pipeline")
            for n, s in sorted(res["stages"].items()):
                if s["status"] == "n/a":
                    continue
                st.markdown(md(f"{BADGE.get(s['status'], '')} **{n}. {s['stage']}** {('- ' + s['summary']) if s['summary'] else ''}"))
            if res["flags"]:
                st.markdown("##### Flags for a human")
                for f in res["flags"]:
                    st.warning(md(f))
        with right:
            st.markdown("##### Who is this?")
            if res["identity"]:
                st.json(res["identity"], expanded=True)
            if res["qualification"]:
                st.markdown(f"Decision: **{res['qualification']['decision']}**")
                st.caption(md("; ".join(res["qualification"]["reasons"])))
            with st.expander(f"AI extraction ({res['extraction']['method']})"):
                st.json(res["extraction"])
                for n in res["extract_notes"]:
                    st.caption(md(f"⚠ {n}"))
            if res.get("quote_id"):
                q = next(q for q in w.crm.quotes if q["id"] == res["quote_id"])
                st.markdown(f"##### Quote {q['id']} · {q['status']}")
                st.dataframe(pd.DataFrame([{k: l[k] for k in ("sku", "description", "yards", "list_price",
                                                               "total_discount", "unit_price", "cut_fee", "line_total")}
                                           for l in q["lines"]]), hide_index=True, width="stretch")
            if res["email"]:
                pending = any(r["request"] == sel and r["status"] == "Open" for r in w.reviews)
                st.markdown("##### Customer email " + ("(draft, waiting on review)" if pending else "(draft)"))
                st.text_area("Subject: " + res["email"]["subject"], res["email"]["body"], height=300, key=f"em-{sel}")
    else:
        st.info("Click **▶ Next request** to step through the inbox, or **⏭ Process all**.")

# ---------------------------------------------------------------- review queue
with tab_review:
    st.caption("Everything the policy wasn't sure about lands here (and as a CRM Task). Approve runs the deferred action.")
    if not w.reviews:
        st.info("Nothing to review yet.")
    for rv in sorted(w.reviews, key=lambda r: r["status"] != "Open"):
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            req = w.results[rv["request"]]["request"]
            c1.markdown(f"**{rv['id']}** · {rv['request']} · {req['name'] or req['email']} · *{rv['stage']}* · owner: {rv['owner']}")
            c1.markdown(md(f"**Why:** {rv['reason']}"))
            c1.markdown(md(f"**Proposed:** {rv['proposed']}"))
            if rv["status"] == "Open":
                if c2.button("Approve", key=f"a-{rv['id']}", type="primary", width="stretch"):
                    w.approve(rv["id"])
                    st.rerun()
                if c2.button("Reject", key=f"r-{rv['id']}", width="stretch"):
                    w.reject(rv["id"])
                    st.rerun()
            else:
                c2.markdown(f"`{rv['status']}`")

# ---------------------------------------------------------------- CRM
def df(records, cols=None):
    if not records:
        return pd.DataFrame()
    d = pd.DataFrame(records)
    for c in d.columns:
        if d[c].map(lambda v: isinstance(v, (list, dict))).any():
            d[c] = d[c].map(lambda v: json.dumps(v, default=str) if isinstance(v, (list, dict)) else v)
    return d[cols] if cols else d


with tab_crm:
    st.caption("Mock Salesforce. Source of truth for people, companies, trade status, opportunities and quotes.")
    st.markdown("**Leads**")
    st.dataframe(df(w.crm.leads, ["id", "name", "company", "email", "source", "status", "status_reason", "converted_contact_id"]),
                 hide_index=True, width="stretch")
    a, b = st.columns(2)
    a.markdown("**Accounts**")
    a.dataframe(df(w.crm.accounts), hide_index=True, width="stretch")
    b.markdown("**Contacts**")
    b.dataframe(df(w.crm.contacts), hide_index=True, width="stretch")
    st.markdown("**Opportunities**")
    st.dataframe(df(w.crm.opportunities), hide_index=True, width="stretch")
    st.markdown("**Quotes**")
    st.dataframe(df(w.crm.quotes, ["id", "opp_id", "status", "total", "budgetary", "valid_until", "reservation_id", "flags"])
                 if w.crm.quotes else pd.DataFrame(), hide_index=True, width="stretch")
    st.markdown("**Tasks**")
    st.dataframe(df(w.crm.tasks), hide_index=True, width="stretch")

# ---------------------------------------------------------------- ERP
with tab_erp:
    st.caption("Mock NetSuite. Source of truth for items, price, inventory by dye lot, and orders.")
    inv = pd.DataFrame(w.erp.lots)
    inv["available"] = inv["on_hand"] - inv["reserved"]
    st.markdown("**Inventory by dye lot**")
    st.dataframe(inv[["sku", "fabric", "color", "status", "list_price", "lot", "on_hand", "reserved", "available"]],
                 hide_index=True, width="stretch")
    st.markdown("**Sales orders (samples + reservations)**")
    st.dataframe(df(w.erp.sales_orders), hide_index=True, width="stretch")

# ---------------------------------------------------------------- audit
with tab_log:
    st.caption("Every system call, with the real API it maps to. This doubles as the integration spec.")
    systems = sorted({e["system"] for e in w.log.events})
    pick = st.multiselect("Systems", systems, default=systems)
    ev = [e for e in w.log.events if e["system"] in pick]
    st.dataframe(pd.DataFrame(ev) if ev else pd.DataFrame(), hide_index=True, width="stretch")
