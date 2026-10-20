"""Seed the demo with the workbook history, including the rep's qualification decisions.

Qualification is manual for new senders, so the history needs a person's decisions to move past
step one (Dana Ruiz, for example, is a new sender in the workbook). The decisions are in
data/seed_decisions.json and are applied right after each request, in time order, as they
would have happened.
"""
from __future__ import annotations

import json
from pathlib import Path

DECISIONS = Path(__file__).resolve().parent / "data" / "seed_decisions.json"
QUALIFICATION = ("qualify_and_sample", "qualify_and_quote")


def seed(w, decisions: dict | None = None):
    decisions = decisions if decisions is not None else {
        k: v for k, v in json.loads(DECISIONS.read_text()).items() if not k.startswith("_")}
    w.extractor.prefetch(w.pending())  # read the seeded emails in parallel first
    for req in list(w.pending()):
        w.process(req)
        choice = decisions.get(req["id"])
        for rv in [r for r in w.reviews if r["request"] == req["id"] and r["status"] == "Open"
                   and r["action"] in QUALIFICATION]:
            if choice == "qualify":
                w.approve(rv["id"], by="rep (seeded)")
            elif choice == "reject":
                w.reject(rv["id"], by="rep (seeded)")
    return w
