"""Two ways to start the demo.

clean (the default): only what Perennials already has on day one, i.e. NetSuite's items, dye lots and
price rules and Salesforce's existing accounts and contacts. No requests have been processed, so a new
customer's journey (Dana Ruiz) is the only thing on screen.

history: the 27 workbook requests already processed, including the rep's qualification decisions
(qualification is manual for new senders, so the history needs a person's decisions to move past step
one). The decisions are in data/seed_decisions.json; Workflow.process_all replays each one right after
its request. Use it to explore the edge cases.
"""
from __future__ import annotations

import json
from pathlib import Path

DECISIONS = Path(__file__).resolve().parent / "data" / "seed_decisions.json"


def load_decisions(path: Path = DECISIONS) -> dict:
    return {k: v for k, v in json.loads(Path(path).read_text()).items() if not k.startswith("_")}


def seed(w, decisions: dict | None = None):
    w.process_all(decisions if decisions is not None else load_decisions())
    return w


def clean(w):
    """Drop the workbook's requests: accounts, contacts, inventory and pricing stay as loaded.
    Live submissions are timed from the first workbook request, so the simulated clock still works."""
    w.demo_clock = min(r["received"] for r in w.inbox)
    w.inbox = []
    return w
