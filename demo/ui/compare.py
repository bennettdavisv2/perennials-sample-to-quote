"""Old vs new, side by side, for one customer's sample-to-quote journey."""
from __future__ import annotations

import streamlit as st

from demo import baseline

from .common import acct_name, md, system_header, wf


def render():
    w = wf()
    system_header("compare", "Old vs New", "the same customer journey, done by hand today vs with the workflow")
    js = baseline.journeys(w)
    order = sorted(js, key=lambda a: (-len(js[a]), a))
    acct = st.selectbox("Customer journey", order, format_func=lambda a: f"{acct_name(w, a)} · {' → '.join(js[a])}")
    rids = js[acct]
    t = baseline.totals(w, rids)

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("### Today: manual")
        m = st.columns(3)
        m[0].metric("Touches", t["old"]["people touches"])
        m[1].metric("Minutes", f"{t['old']['hands-on minutes']:.0f}")
        m[2].metric("Retyped", t["old"]["fields retyped"])
        m = st.columns(3)
        m[0].metric("Emails", t["old"]["emails written"])
        m[1].metric("Wait (h)", t["old"]["est. hours waiting"])
    with right:
        st.markdown("### With the workflow")
        m = st.columns(3)
        m[0].metric("Touches", t["new"]["people touches"])
        m[1].metric("Minutes", f"{t['new']['hands-on minutes']:.0f}")
        m[2].metric("Retyped", 0)
        m = st.columns(3)
        m[0].metric("Emails", 0, help="Customer emails are drafted from ERP data, not written by a person")
        m[1].metric("Wait (h)", t["new"]["est. hours waiting"])
        m[2].metric("Automated", t["automated actions"])
    st.caption("Touches = steps a person does · Retyped = values copied from one system or form into another · "
               "Wait = hours work sits in someone else's inbox. "
               "Manual-side minutes, fields, emails and waits are illustrative estimates (demo/baseline.py), "
               "not measurements. Each automated action below replaces the manual step on its left.")

    for rid in rids:
        res = w.results[rid]
        old = baseline.old_steps(w, rid)
        auto, human = baseline.new_steps(w, rid)
        with st.expander(f"{rid} · {res['request']['type']} · {res['outcome']}", expanded=rid == rids[-1]):
            a, b = st.columns(2, gap="large")
            with a:
                st.markdown(f"**Today: {len(old)} manual steps**")
                for s in old:
                    extra = ", ".join(x for x in [f"{s.fields} fields retyped" if s.fields else "",
                                                  f"{s.emails} email" if s.emails else "",
                                                  "waits in another inbox" if s.waits else ""] if x)
                    st.markdown(md(f"- **{s.actor}**: {s.what} · {s.minutes:g} min" + (f" · {extra}" if extra else "")))
            with b:
                st.markdown(f"**New: {len(auto)} automated, {len(human)} by a person**")
                for e in auto:
                    st.markdown(md(f"- **{e['system']}** {e['action']}: {e['detail']}"))
                for r in [r for r in w.reviews if r["request"] == rid]:
                    st.markdown(md(f"- **Sales rep** reviews {r['id']} ({r['stage']}): {r['status']}"))
                if res["email"]:
                    st.markdown(md(f"- Customer email drafted: *{res['email']['subject']}*"))
