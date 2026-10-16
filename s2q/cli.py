"""Headless run: process every inbound request and print what happened.

    python -m s2q.cli               # auto: Claude if ANTHROPIC_API_KEY is set, else rules
    python -m s2q.cli --rules       # force offline rules
    python -m s2q.cli --approve-all # also approve every review item (simulates a rep)
    python -m s2q.cli --verbose     # include stage details and email drafts
"""
from __future__ import annotations

import argparse

from .workflow import Workflow

ICON = {"done": "OK ", "review": "REV", "blocked": "BLK", "skipped": "-- ", "n/a": "   ", "waiting": "...", }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", action="store_true")
    ap.add_argument("--approve-all", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--data")
    a = ap.parse_args()

    wf = Workflow(a.data, mode="rules" if a.rules else "auto") if a.data else Workflow(mode="rules" if a.rules else "auto")
    print(f"Extractor: {wf.extractor.status}\n")
    wf.process_all()
    if a.approve_all:
        for rv in list(wf.reviews):
            if rv["status"] == "Open":
                wf.approve(rv["id"], by="cli")

    for rid, res in wf.results.items():
        r = res["request"]
        stages = " ".join(f"{n}:{ICON.get(s['status'], s['status'])}" for n, s in sorted(res["stages"].items()))
        print(f"{rid}  {r['received']:%m-%d %H:%M}  {(r['name'] or r['email'])[:22]:22}  {stages}  -> {res['outcome']}")
        if a.verbose:
            for n, s in sorted(res["stages"].items()):
                if s["summary"]:
                    print(f"      [{n}] {s['summary']}")
            for f in res["flags"]:
                print(f"      ! {f}")
            if res["email"]:
                print("      --- email draft ---")
                print("\n".join("      | " + ln for ln in res["email"]["body"].splitlines()))
            print()

    print(f"\nReview queue: {sum(1 for r in wf.reviews if r['status'] == 'Open')} open of {len(wf.reviews)}")
    for rv in wf.reviews:
        print(f"  {rv['id']} {rv['request']} [{rv['status']}] {rv['stage']}: {rv['reason'][:110]}")
    print(f"\nCRM: {len(wf.crm.leads)} leads, {len(wf.crm.accounts)} accounts, {len(wf.crm.opportunities)} opps, "
          f"{len(wf.crm.quotes)} quotes | ERP: {len(wf.erp.sales_orders)} sales orders | audit events: {len(wf.log.events)}")


if __name__ == "__main__":
    main()
