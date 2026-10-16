"""Lead qualification policy.

Deterministic on purpose: the extractor (LLM or rules) supplies *signals*; this table
makes the *decision* and says why. Sales ops can read and change it.

Decisions:
  spam         -> dropped at the website, no CRM record
  disqualified -> lead closed (e.g. Do Not Sell account), no samples
  non_trade    -> real person, not trade: no free trade samples, nurture + retail path
  qualified    -> trade: free samples, opportunity created
  review       -> a person decides (mixed or missing signals)
"""
from __future__ import annotations

from .extract import is_free_email


def decide(ext: dict, ident: dict, req: dict) -> dict:
    acct = ident.get("account")
    seg = ext["segment_hint"]
    free = is_free_email(req["email"])
    reasons = list(ext.get("signals", []))

    if seg == "spam":
        return {"decision": "spam", "reasons": reasons + ["spam content"]}
    if acct and acct.get("status") == "Do Not Sell":
        return {"decision": "disqualified", "reasons": [f"account {acct['id']} is '{acct['type']}' / Do Not Sell"]}
    if acct and str(acct.get("type", "")).startswith("Trade"):
        return {"decision": "qualified", "reasons": [f"matched trade account {acct['id']} ({ident['match']})"]}
    if acct and acct.get("type", "").startswith("Consumer"):
        return {"decision": "non_trade", "reasons": [f"matched consumer account {acct['id']}"]}
    if seg == "competitor":
        return {"decision": "review", "reasons": reasons + ["looks like a reseller/competitor but no CRM match"]}
    if seg in ("consumer", "student"):
        return {"decision": "non_trade", "reasons": reasons + [f"segment: {seg}"]}
    if seg == "trade" and not free:
        return {"decision": "qualified", "reasons": reasons + ["business email domain"]}
    if seg == "trade" and free:
        return {"decision": "review", "reasons": reasons + ["trade language but personal email domain: verify (resale cert / website)"]}
    return {"decision": "review", "reasons": reasons + ["not enough signal to qualify automatically"]}
