"""Seed the demo with the workbook history, including the rep's qualification decisions.

Qualification is manual for new senders, so the history needs a person's decisions to move past
step one (Dana Ruiz, for example, is a new sender in the workbook). The decisions are in
data/seed_decisions.json; Workflow.process_all replays each one right after its request.
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
