"""Streamlit front end for the sample-to-quote PoC.

    streamlit run app.py

Layout: a control bar and headline numbers, then four tabs:
  Requests       pick a request on the left, read its story on the right
  Review queue   everything waiting on a person, with approve / reject
  Records        the mock CRM (Salesforce) and ERP (NetSuite) tables
  Integration log  every system call and the real API it maps to
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from s2q.workflow import STAGES, Workflow

st.set_page_config(page_title="Perennials Sample-to-Quote", page_icon="🧵", layout="wide",
                   initial_sidebar_state="collapsed")

SYSTEMS = {1: "Website → CRM", 2: "CRM", 3: "ERP + CRM", 4: "Email → CRM", 5: "ERP → CRM", 6: "ERP"}
STAGE_STATUS = {"done": "✅ Done", "review": "🟡 Needs review", "blocked": "⛔ Blocked", "skipped": "➖ Skipped",
                "waiting": "⏳ Waiting", "n/a": "· Not applicable"}
DECISION = {"qualified": "✅ Qualified trade customer", "non_trade": "💬 Not trade: nurture, no free samples",
            "disqualified": "⛔ Disqualified", "spam": "⛔ Spam", "review": "🟡 Needs a person to decide"}


def md(text) -> str:
    """Escape $ so Streamlit markdown doesn't render prices as LaTeX."""
    return str(text).replace("$", "\\$")


def wf() -> Workflow:
    if "wf" not in st.session_state:
        st.session_state.wf = Workflow(mode=st.session_state.get("mode", "auto"))
    return st.session_state.wf


def select(rid: str | None):
    """Point the detail panel at a request and clear the table's own selection."""
    st.session_state.selected = rid
    st.session_state.table_ver = st.session_state.get("table_ver", 0) + 1


def open_reviews(rid: str | None = None):
    return [r for r in w.reviews if r["status"] == "Open" and (rid is None or r["request"] == rid)]


def short_status(rid: str) -> str:
    res = w.results.get(rid)
    if not res:
        return "⚪ In inbox"
    if open_reviews(rid):
        return "🟡 Needs review"
    if res["outcome"].startswith(("Spam", "Disqualified", "Blocked", "Quote rejected")):
        return "⛔ Stopped"
    if res["outcome"].startswith("Non-trade"):
        return "💬 Nurture"
    return "✅ Done"


def review_buttons(rv: dict, where: str):
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


def money(x) -> str:
    return f"${x:,.2f}"


# ---------------------------------------------------------------- sidebar: settings only
with st.sidebar:
    st.subheader("Settings")
    mode = st.radio("How emails are read", ["auto", "rules"], horizontal=True,
                    help="Website requests arrive structured (exact SKUs from the cart), so only emails are read. "
                         "auto = Claude reads the email (rules run as a cross-check) when ANTHROPIC_API_KEY "
                         "is set. rules = deterministic parser only.")
    if mode != st.session_state.get("mode", "auto"):
        st.session_state.mode = mode
        st.session_state.pop("wf", None)
        select(None)
    w = wf()
    st.caption(f"Extractor in use: **{w.extractor.status}**")
    st.divider()
    st.caption("CRM and ERP are in-memory mocks seeded from `data/perennials_sample_data.xlsx`. "
               "Each request is processed at its own received time. Reset to start over.")

# ---------------------------------------------------------------- header + controls
st.title("Perennials · Sample-to-Quote")
st.markdown("Inbound sample and quote requests are read, matched to the CRM, qualified, priced, and held in "
            "inventory automatically. Anything uncertain is sent to a person instead of guessed.")

with st.expander("How the workflow works", expanded=not w.results):
    for label, nums, how in [
            ("Sample requests (WEB-…)", (1, 2, 3), "Arrive from the website cart with exact SKUs: nothing to interpret."),
            ("Quote requests (EML-…)", (4, 5, 6), "Arrive by email in free text: read by Claude (or rules), then validated.")]:
        st.markdown(f"**{label}**: {how}")
        for col, n in zip(st.columns(3), nums):
            col.markdown(f"**{n}. {STAGES[n]}**  \n:gray[{SYSTEMS[n]}]")

c1, c2, c3, _ = st.columns([1, 1, 1, 2])
if c1.button("▶ Process next", type="primary", width="stretch", disabled=not w.pending()):
    select(w.process_next()["request"]["id"])
if c2.button("⏭ Process all", width="stretch", disabled=not w.pending()):
    w.process_all()
if c3.button("↺ Reset", width="stretch"):
    st.session_state.pop("wf", None)
    select(None)
    st.rerun()

held = sum(a["yards"] for so in w.erp.sales_orders if so["type"] == "Reservation" and not so["status"].startswith("Released")
           for ln in so["lines"] for a in ln["allocation"])
m = st.columns(5)
m[0].metric("Processed", f"{len(w.results)} / {len(w.inbox)}")
m[1].metric("Sample orders", sum(1 for so in w.erp.sales_orders if so["type"] == "Sample"))
m[2].metric("Quotes sent", sum(1 for q in w.crm.quotes if q["status"] == "Sent"))
m[3].metric("Waiting on a person", len(open_reviews()))
m[4].metric("Yards on hold", f"{held:,.0f}")

tab_req, tab_rev, tab_rec, tab_log = st.tabs(
    ["Requests", f"Review queue ({len(open_reviews())})", "CRM & ERP records", "Integration log"])


# ---------------------------------------------------------------- requests
def render_detail(rid: str):
    req = next(r for r in w.inbox if r["id"] == rid)
    res = w.results.get(rid)

    st.subheader(f"{rid} · {req['name'] or req['email']}")
    st.caption(f"{req['type']} via {req['channel']} · {req['company'] or 'no company given'} · "
               f"{req['email']} · {req['received']:%b %d, %H:%M} UTC")
    cart = req.get("cart")
    if cart:
        # As it arrives from the site: exact colorways from the product pages, plus checkout fields.
        st.markdown("**Submitted on the website** (cart from product pages)")
        lines = cart.get("quote_lines") or [{"sku": s} for s in cart.get("skus", [])]
        rows = []
        for ln in lines:
            it = w.erp.get_item(ln["sku"]) or {}
            row = {"SKU": ln["sku"], "Fabric": it.get("fabric", "not in ERP"), "Color": it.get("color", "")}
            if "length" in ln:
                row |= {"Length": f"{ln['length']:g} {ln.get('unit', '')}", "Date needed": ln.get("date_needed") or "",
                        "CFA": ln.get("cfa") or ""}
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption(f"Project type: **{cart.get('project_type') or 'not given'}** · "
                   f"Project name: **{cart.get('project_name') or 'not given'}**")
        if cart.get("note"):
            st.markdown("**Order note** (the only free text on the form)")
            st.info(md(cart["note"]))
    else:
        st.markdown("**Email**")
        st.info(md(req["message"]))

    if not res:
        st.write("Not processed yet. Requests are handled in the order they arrived; "
                 "click **▶ Process next** to continue.")
        return
    ext, s = res["extraction"], short_status(rid)
    banner = {"✅": st.success, "🟡": st.warning, "⛔": st.error, "💬": st.info}[s[0]]
    banner(md(f"**Result:** {res['outcome']}"))

    # What happened at each stage this request touches.
    st.markdown("##### What happened")
    nums = [1, 2, 3] if req["type"].lower().startswith("sample") else [4, 5, 6]
    for col, n in zip(st.columns(3), nums):
        stage = res["stages"].get(n, {"status": "n/a", "summary": ""})
        with col.container(border=True, height="stretch"):
            st.markdown(f"**{n}. {STAGES[n]}**")
            st.caption(SYSTEMS[n])
            st.markdown(STAGE_STATUS.get(stage["status"], stage["status"]))
            if stage["summary"]:
                st.caption(md(stage["summary"]))

    # Needs attention: flags plus the review items to resolve them, right here.
    pending = open_reviews(rid)
    if pending or res["flags"]:
        st.markdown("##### Needs attention")
        for f in res["flags"]:
            st.warning(md(f))
        for rv in pending:
            with st.container(border=True):
                st.markdown(md(f"**{rv['stage']} review** ({rv['id']}, owner: {rv['owner']})  \n"
                               f"Proposed: {rv['proposed']}"))
                review_buttons(rv, "detail")

    left, right = st.columns(2)
    with left:
        st.markdown("##### Who is this?")
        ident, q = res["identity"], res["qualification"]
        if ident:
            st.markdown(md(f"**CRM match:** {ident['match']}"))
            if ident["account"]:
                st.markdown(md(f"**Account:** {ident['account']}"))
            if ident["contact"]:
                st.markdown(md(f"**Contact:** {ident['contact']}"))
        if q:
            st.markdown(f"**Decision:** {DECISION.get(q['decision'], q['decision'])}")
            st.markdown("\n".join(f"- {md(r)}" for r in q["reasons"]))
    with right:
        st.markdown("##### What did they ask for?")
        if ext["method"] == "web cart":
            st.markdown("Exact colorways from the cart, so there is nothing to interpret: "
                        + (", ".join(i["reference"] for i in ext["items"]) or "none") + ".")
        else:
            st.caption(f"Read from the email by **{ext['method']}**")
            rows = []
            for it in ext["items"]:
                names = [f"{i['fabric']} {i['color']}" for s in it["skus"] if (i := w.erp.get_item(s))]
                qty = f"{it['quantity']:g} {it['unit'] or ''}".strip() if it["quantity"] is not None else ""
                note = "unclear color" if it["ambiguous"] else "inferred" if it.get("inferred") else ""
                rows.append({"Customer wrote": it["reference"], "Matched to": ", ".join(names),
                             "Quantity": qty, "Note": note})
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            else:
                st.caption("No specific fabrics named.")
        tags = [t for t, on in [("budgetary pricing only", ext.get("budgetary")), ("urgent", ext.get("urgent")),
                                (f"needs by {ext.get('need_by')}", ext.get("need_by")),
                                ("revises an earlier request", ext.get("revision")),
                                ("asks for 'everything'", ext.get("wildcard"))] if on]
        st.caption(f"Segment: **{ext['segment_hint']}**" + (" · " + " · ".join(tags) if tags else ""))

    if res.get("quote_id"):
        quote = next(x for x in w.crm.quotes if x["id"] == res["quote_id"])
        st.markdown(f"##### Quote {quote['id']}")
        lines = pd.DataFrame([{
            "Fabric": l["description"], "SKU": l["sku"], "Yards": l["yards"], "List $/yd": l["list_price"],
            "Discount": f"{l['total_discount'] * 100:.0f}%", "Price $/yd": l["unit_price"],
            "Cut fee": l["cut_fee"], "Line total": l["line_total"]} for l in quote["lines"]])
        st.dataframe(lines, hide_index=True, width="stretch", column_config={
            c: st.column_config.NumberColumn(format="$%.2f") for c in ("List $/yd", "Price $/yd", "Cut fee", "Line total")})
        so = next((x for x in w.erp.sales_orders if x["id"] == quote.get("reservation_id")), None)
        hold = (f"{so['id']} until {so['hold_expires']:%b %d}" + (" (released)" if so["status"].startswith("Released") else "")
                if so else "none")
        st.markdown(md(f"**Total {money(quote['total'])}** · Status: **{quote['status']}** · "
                       f"Valid until {quote['valid_until']:%b %d} · Inventory hold: {hold}"))

    if res["email"]:
        waiting = " (draft, not sent until the review is approved)" if pending else ""
        st.markdown(f"##### Email to customer{waiting}")
        with st.container(border=True):
            st.markdown(md(f"**Subject:** {res['email']['subject']}"))
            st.code(res["email"]["body"], language=None, wrap_lines=True)

    with st.expander("Raw data (structured request JSON)"):
        st.caption(f"Read by: {ext['method']}")
        for n in res["extract_notes"]:
            st.caption(md(f"⚠ {n}"))
        st.json(ext, expanded=False)


with tab_req:
    left, right = st.columns([2, 3], gap="large")
    with left:
        table = pd.DataFrame([{"ID": r["id"], "Status": short_status(r["id"]), "From": r["name"] or r["email"]}
                              for r in w.inbox])
        st.caption("Click a row to see the details.")
        event = st.dataframe(table, hide_index=True, width="stretch", height=35 * (len(table) + 1) + 3,
                             on_select="rerun", selection_mode="single-row",
                             column_config={"ID": st.column_config.TextColumn(width="small"),
                                            "Status": st.column_config.TextColumn(width="medium")},
                             key=f"inbox-{st.session_state.get('table_ver', 0)}")
        if event.selection.rows:
            st.session_state.selected = table.iloc[event.selection.rows[0]]["ID"]
    with right:
        rid = st.session_state.get("selected") or (list(w.results)[-1] if w.results else None)
        if rid:
            render_detail(rid)
        else:
            st.info("Click **▶ Process next** to handle the first request, or **⏭ Process all**. "
                    "You can also click any row to read the incoming message.")

# ---------------------------------------------------------------- review queue
with tab_rev:
    st.caption("Everything the rules weren't sure about lands here, and as a Task in the CRM. "
               "Approving runs the waiting action (send the samples, or send the quote).")
    todo = open_reviews()
    if not todo:
        st.success("Nothing waiting on a person." if w.results else "Nothing yet. Process some requests first.")
    for rv in todo:
        req = w.results[rv["request"]]["request"]
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**{rv['request']} · {req['name'] or req['email']}**: {rv['stage']} review")
                st.markdown("\n".join(f"- {md(r)}" for r in reasons(rv)))
                st.markdown(md(f"**Proposed:** {rv['proposed']}"))
                st.caption(f"{rv['id']} · owner: {rv['owner']}")
            with c2:
                review_buttons(rv, "queue")
    done = [r for r in w.reviews if r["status"] != "Open"]
    if done:
        with st.expander(f"Resolved ({len(done)})"):
            st.dataframe(pd.DataFrame([{"Review": r["id"], "Request": r["request"], "Stage": r["stage"],
                                        "Outcome": r["status"]} for r in done]), hide_index=True, width="stretch")


# ---------------------------------------------------------------- records
def table(rows: list[dict], cols: dict, money_cols=(), height="auto"):
    """Show rows with friendly column names (cols maps label -> function or key)."""
    if not rows:
        st.caption("No records yet.")
        return
    d = pd.DataFrame([{label: (f(r) if callable(f) else r.get(f)) for label, f in cols.items()} for r in rows])
    st.dataframe(d, hide_index=True, width="stretch", height=height,
                 column_config={c: st.column_config.NumberColumn(format="$%.2f") for c in money_cols})


acct_name = lambda aid: (w.crm.account(aid) or {}).get("name", aid)  # noqa: E731

with tab_rec:
    crm_col, erp_col = st.tabs(["CRM (Salesforce)", "ERP (NetSuite)"])
    with crm_col:
        st.caption("Source of truth for people and companies, trade status, opportunities, quotes, and review tasks.")
        t = st.tabs(["Leads", "Accounts", "Contacts", "Opportunities", "Quotes", "Tasks"])
        with t[0]:
            table(w.crm.leads, {"ID": "id", "Name": "name", "Company": "company", "Email": "email", "Source": "source",
                                "Status": "status", "Why": "status_reason"})
        with t[1]:
            table(w.crm.accounts, {"ID": "id", "Name": "name", "Type": "type", "Status": "status"})
        with t[2]:
            table(w.crm.contacts, {"ID": "id", "Name": "name", "Account": lambda c: acct_name(c["account_id"]),
                                   "Email": "email", "Other emails": lambda c: ", ".join(c.get("alt_emails", []))})
        with t[3]:
            table(w.crm.opportunities, {"ID": "id", "Name": "name", "Account": lambda o: acct_name(o["account_id"]),
                                        "Stage": "stage", "Amount": "amount",
                                        "Sample orders": lambda o: ", ".join(o["sample_orders"])}, money_cols=["Amount"])
        with t[4]:
            table(w.crm.quotes, {"Quote": "id", "Opportunity": "opp_id", "Status": "status", "Total": "total",
                                 "Budgetary": "budgetary", "Valid until": lambda q: f"{q['valid_until']:%Y-%m-%d}",
                                 "Hold": "reservation_id", "Flags": lambda q: len(q["flags"])}, money_cols=["Total"])
        with t[5]:
            table(w.crm.tasks, {"ID": "id", "Owner": "owner", "Subject": "subject", "Request": "related_to",
                                "Status": "status"})
    with erp_col:
        st.caption("Source of truth for items, prices, inventory by dye lot, sample orders, and inventory holds.")
        st.markdown("**Inventory by dye lot**")
        table(w.erp.lots, {"SKU": "sku", "Fabric": "fabric", "Color": "color", "Status": "status", "Dye lot": "lot",
                           "On hand (yd)": "on_hand", "Reserved (yd)": "reserved",
                           "Available (yd)": lambda l: max(l["on_hand"] - l["reserved"], 0), "List $/yd": "list_price"},
              money_cols=["List $/yd"], height=35 * (len(w.erp.lots) + 1) + 3)
        st.markdown("**Orders** (sample orders, CFA cuttings, and inventory holds)")

        def order_lines(so):
            if so["type"] == "Sample":
                return ", ".join(l["sku"] for l in so["lines"])
            if so["type"] == "CFA":
                return ", ".join(f"{l['sku']} cutting from {l['lot']}" for l in so["lines"])
            return "; ".join(f"{l['sku']} " + " + ".join(f"{a['yards']:g} yd from {a['lot']}" for a in l["allocation"])
                             for l in so["lines"])

        table(w.erp.sales_orders, {"Order": "id", "Type": "type", "Customer": "customer", "For quote": "quote_id",
                                   "Status": "status", "Lines": order_lines,
                                   "Hold until": lambda s: f"{s['hold_expires']:%Y-%m-%d}" if s.get("hold_expires") else ""})

# ---------------------------------------------------------------- integration log
with tab_log:
    st.caption("Every call the workflow made, with the real Salesforce / NetSuite API it stands for. "
               "This doubles as the integration spec for engineering.")
    f1, f2 = st.columns([1, 3])
    rq = f1.selectbox("Request", ["All"] + list(w.results))
    systems = sorted({e["system"] for e in w.log.events})
    pick = f2.multiselect("Systems", systems, default=systems)
    ev = [e for e in w.log.events if e["system"] in pick and rq in ("All", e["request"])]
    table(ev, {"#": "seq", "Time": "sim_time", "Request": "request", "System": "system", "Action": "action",
               "Detail": "detail", "Real API": "maps_to"})
