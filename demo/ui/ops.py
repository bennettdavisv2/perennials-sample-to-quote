"""Ops console: every request's full story, the review queue, and the integration log."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from s2q.workflow import STAGES

from .common import md, money, open_reviews, reasons, review_buttons, review_message, table, wf

SYSTEMS = {1: "Website → CRM", 2: "CRM", 3: "ERP + CRM", 4: "Website / email → CRM", 5: "ERP → CRM", 6: "ERP"}
STAGE_STATUS = {"done": "Done", "review": "Needs review", "blocked": "Blocked", "skipped": "Skipped",
                "waiting": "Waiting", "n/a": "Not applicable"}
DECISION = {"qualified": "Qualified trade customer", "disqualified": "Disqualified", "spam": "Spam",
            "review": "A rep qualifies"}
STOPPED = ("Spam", "Disqualified", "Blocked", "Quote rejected", "Sample request rejected", "Dismissed")


def short_status(w, rid: str) -> str:
    res = w.results.get(rid)
    if not res:
        return "In inbox"
    if open_reviews(w, rid):
        return "Needs review"
    if res["outcome"].startswith(STOPPED):
        return "Stopped"
    return "Done"


def render_detail(w, rid: str):
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
        return
    ext, s = res["extraction"], short_status(w, rid)
    banner = {"Done": st.success, "Needs review": st.warning, "Stopped": st.error, "In inbox": st.info}[s]
    banner(md(f"**Result:** {res['outcome']}"))

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

    pending = open_reviews(w, rid)
    if pending or res["flags"]:
        st.markdown("##### Needs attention")
        for f in res["flags"]:
            st.warning(md(f))
        for rv in pending:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(md(f"**{rv['stage']} review** ({rv['id']}, owner: {rv['owner']})  \n"
                                   f"Proposed: {rv['proposed']}"))
                    review_message(rv)
                with c2:
                    review_buttons(w, rv, "detail")

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
                                ("CFA requested", ext.get("cfa_requested"))] if on]
        st.caption(f"Segment: **{ext['segment_hint']}**" + (" · " + " · ".join(tags) if tags else ""))

    if res.get("quote_id"):
        quote = next(x for x in w.crm.quotes if x["id"] == res["quote_id"])
        st.markdown(f"##### Quote {quote['id']}")
        quote_lines(quote)
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
            st.caption(md(f"Note: {n}"))
        st.json(ext, expanded=False)


def quote_lines(quote: dict):
    lines = pd.DataFrame([{
        "Fabric": l["description"], "SKU": l["sku"], "Yards": l["yards"], "List $/yd": l["list_price"],
        "Discount": f"{l['total_discount'] * 100:.0f}%", "Price $/yd": l["unit_price"],
        "Cut fee": l["cut_fee"], "Line total": l["line_total"]} for l in quote["lines"]])
    st.dataframe(lines, hide_index=True, width="stretch", column_config={
        c: st.column_config.NumberColumn(format="$%.2f") for c in ("List $/yd", "Price $/yd", "Cut fee", "Line total")})


def render():
    w = wf()
    st.title("Ops console")
    st.caption("Behind the scenes: every request's full story, the review queue, and every system call. "
               "The CRM and ERP pages show the same data the way each system would.")

    tab_req, tab_rev, tab_log = st.tabs(["Requests", f"Review queue ({len(open_reviews(w))})", "Integration log"])
    with tab_req:
        left, right = st.columns([2, 3], gap="large")
        with left:
            inbox = sorted(w.inbox, key=lambda r: r["received"], reverse=True)
            tbl = pd.DataFrame([{"ID": r["id"], "Status": short_status(w, r["id"]), "From": r["name"] or r["email"]}
                                for r in inbox])
            st.caption("Newest first. Click a row to see the details.")
            event = st.dataframe(tbl, hide_index=True, width="stretch", height=35 * (len(tbl) + 1) + 3,
                                 on_select="rerun", selection_mode="single-row",
                                 column_config={"ID": st.column_config.TextColumn(width="small"),
                                                "Status": st.column_config.TextColumn(width="medium")},
                                 key="ops-inbox")
            if event.selection.rows:
                st.session_state.selected = tbl.iloc[event.selection.rows[0]]["ID"]
        with right:
            rid = st.session_state.get("selected") or inbox[0]["id"]
            render_detail(w, rid)

    with tab_rev:
        st.caption("Everything the rules weren't sure about lands here, and as a Task in the CRM. "
                   "Approving runs the waiting action (send the samples, or send the quote).")
        todo = open_reviews(w)
        if not todo:
            st.success("Nothing waiting on a person.")
        for rv in todo:
            req = w.results[rv["request"]]["request"]
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**{rv['request']} · {req['name'] or req['email']}**: {rv['stage']} review")
                    st.markdown("\n".join(f"- {md(r)}" for r in reasons(rv)))
                    st.markdown(md(f"**Proposed:** {rv['proposed']}"))
                    st.caption(f"{rv['id']} · owner: {rv['owner']}")
                    review_message(rv)
                with c2:
                    review_buttons(w, rv, "queue")
        done = [r for r in w.reviews if r["status"] != "Open"]
        if done:
            with st.expander(f"Resolved ({len(done)})"):
                table(done, {"Review": "id", "Request": "request", "Stage": "stage", "Outcome": "status"})

    with tab_log:
        st.caption("Every call the workflow made, with the real Salesforce / NetSuite API it stands for. "
                   "This doubles as the integration spec for engineering.")
        f1, f2 = st.columns([1, 3])
        rq = f1.selectbox("Request", ["All"] + [r["id"] for r in w.inbox])
        systems = sorted({e["system"] for e in w.log.events})
        pick = f2.multiselect("Systems", systems, default=systems)
        ev = [e for e in w.log.events if e["system"] in pick and rq in ("All", e["request"])]
        table(ev, {"#": "seq", "Time": "sim_time", "Request": "request", "System": "system", "Action": "action",
                   "Detail": "detail", "Real API": "maps_to"})
