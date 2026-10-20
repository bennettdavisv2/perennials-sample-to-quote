"""Lead qualification policy.

Known accounts are decided automatically; every new sender is qualified by a person.
The extractor still reads the message (items, project, spam), but what a new sender
*says* about themselves never qualifies them: a rep checks and clicks Qualify or Reject.

Decisions:
  spam         -> dropped at the website, no CRM record
  disqualified -> existing Do Not Sell account: lead closed, account owner notified
  non_trade    -> existing consumer account: no free trade samples, nurture + retail path
  qualified    -> existing trade account, or a lead a rep already qualified
  review       -> new sender (no CRM account): a rep qualifies
"""
from __future__ import annotations


def decide(ext: dict, ident: dict, req: dict) -> dict:
    acct = ident.get("account")
    lead = ident.get("lead")

    # Only drop as spam when the readers agree (segment_alt is set when Claude and the rules differ).
    if ext["segment_hint"] == "spam" and not ext.get("segment_alt"):
        return {"decision": "spam", "reasons": list(ext.get("signals", [])) + ["spam content"]}
    if acct and acct.get("status") == "Do Not Sell":
        return {"decision": "disqualified", "reasons": [f"account {acct['id']} is '{acct['type']}' / Do Not Sell"]}
    if acct and str(acct.get("type", "")).startswith("Trade"):
        return {"decision": "qualified", "reasons": [f"matched trade account {acct['id']} ({ident['match']})"]}
    if acct and acct.get("type", "").startswith("Consumer"):
        return {"decision": "non_trade", "reasons": [f"matched consumer account {acct['id']}"]}
    # No CRM account: a person qualifies.
    if lead and lead.get("status") == "Qualified":
        return {"decision": "qualified", "reasons": [f"qualified by a rep ({lead['id']})"]}
    if lead and lead.get("status") == "Needs Review":
        return {"decision": "review", "reasons": [f"already waiting for a rep to qualify ({lead['id']})"]}
    return {"decision": "review", "reasons": ["new sender (no CRM account): a rep qualifies"]}
