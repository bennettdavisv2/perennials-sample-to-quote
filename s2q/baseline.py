"""Old vs new: today's manual process next to what the workflow did.

Every automated action in the integration log stands in for something a person does by hand
today (retyping a form into Salesforce, emailing order ops to key a NetSuite order, ...).
MANUAL maps each action to that manual step.

The minutes, retyped fields, emails and waits are ILLUSTRATIVE ESTIMATES for the demo, not
measurements. Replace them with numbers from a few days of shadowing the sales and order-ops
team; the comparison recomputes from whatever is in this table.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    actor: str
    what: str
    minutes: float = 0
    fields: int = 0   # values retyped from one system or form into another
    emails: int = 0   # emails written (to the customer or between teams)
    waits: int = 0    # times the work sits in someone else's inbox


# (system, action) in the integration log -> the manual step it replaces. None = no manual equivalent.
MANUAL: dict[tuple[str, str], Step | None] = {
    ("Website", "Inbound received"): Step("CSR", "Reads the form-notification email in the shared inbox", 2),
    ("Email", "Inbound received"): Step("Sales rep", "Reads the customer's email", 2),
    ("Website", "Spam filtered"): Step("CSR", "Reads the spam submission and deletes it", 1),
    ("AI", "Extract request"): Step("Sales rep", "Works out which fabrics, colors and quantities are meant; "
                                                 "looks them up in the catalog", 4),
    ("CRM", "Create lead"): Step("CSR", "Retypes name, company, email, source, project and message into a "
                                        "Salesforce Lead", 4, fields=6),
    ("CRM", "Update lead status"): Step("Sales rep", "Checks the company website / resale certificate and sets "
                                                     "the lead status", 4, fields=2),
    ("CRM", "Create account"): Step("Sales rep", "Converts the lead: creates the Account", 2, fields=3),
    ("CRM", "Create contact"): Step("Sales rep", "Converts the lead: creates the Contact", 2, fields=3),
    ("CRM", "Add alternate email"): Step("Sales rep", "Spots the duplicate person and merges the records "
                                                      "(often missed)", 3, fields=1),
    ("CRM", "Create opportunity"): Step("Sales rep", "Creates the Opportunity and links the contact", 3, fields=5),
    ("CRM", "Update opportunity"): Step("Sales rep", "Updates opportunity stage and amount", 1, fields=2),
    ("CRM", "Create quote"): Step("Sales rep", "Builds the quote in Salesforce, retyping each line from NetSuite, "
                                               "and exports the PDF", 8, fields=8),
    ("CRM", "Supersede quote"): Step("Sales rep", "Marks the old quote superseded before rebuilding it", 2, fields=1),
    ("CRM", "Update quote"): Step("Sales rep", "Updates the quote status", 1, fields=1),
    ("CRM", "Email quote"): Step("Sales rep", "Writes the quote email and attaches the PDF", 4, emails=1),
    ("CRM", "Create review task"): None,  # today the person already is the process
    ("ERP", "Create customer"): Step("Order ops", "Rep emails order ops; ops creates the NetSuite customer from the "
                                                  "Salesforce account", 5, fields=8, emails=1, waits=1),
    ("ERP", "Create sample order"): Step("Order ops", "Rep emails order ops; ops retypes the sample request into a "
                                                      "NetSuite sample order", 5, fields=6, emails=1, waits=1),
    ("ERP", "Price line"): Step("Sales rep", "Looks up list price; works out trade / volume discount and cut fee "
                                             "in a spreadsheet", 3),
    ("ERP", "Reserve inventory"): Step("Order ops", "Rep emails order ops to hold yardage; ops picks a dye lot and "
                                                    "enters a pending order", 6, fields=5, emails=1, waits=1),
    ("ERP", "Release reservation"): Step("Order ops", "Rep emails ops to release the old hold (often forgotten)",
                                         3, fields=1, emails=1),
    ("ERP", "Create CFA order"): Step("Order ops", "Rep asks the warehouse to cut a CFA from the held lot", 4,
                                      fields=3, emails=1, waits=1),
    ("Human", "Approve"): None,  # a decision a person makes in both worlds (counted on the new side)
    ("Human", "Reject"): None,
}
# Today a quote request also gets a holding reply while the rep checks NetSuite for stock and price.
QUOTE_HOLDING_REPLY = Step("Sales rep", "Emails the customer: 'checking stock and pricing, back to you shortly'",
                           2, emails=1, waits=1)
REVIEW = Step("Sales rep", "Reviews the flagged item in the CRM and approves or rejects it", 2)
WAIT_HOURS = 4         # business hours lost each time work waits in someone else's inbox (today)
REVIEW_WAIT_HOURS = 1  # a review task in the rep's CRM queue (new)


def old_steps(w, rid: str) -> list[Step]:
    steps = []
    for e in w.log.events:
        if e["request"] != rid:
            continue
        if (e["system"], e["action"]) == ("CRM", "Update lead status") and "-> Converted" in e["detail"]:
            continue  # part of lead convert, already counted as account/contact
        if (step := MANUAL.get((e["system"], e["action"]))) is not None:
            steps.append(step)
    if w.results[rid]["request"]["type"].lower().startswith("quote"):
        steps.insert(2, QUOTE_HOLDING_REPLY)
    return steps


def new_steps(w, rid: str) -> tuple[list[dict], list[Step]]:
    """(automated events, human steps). Human steps are the reviews this request needed."""
    auto = [e for e in w.log.events if e["request"] == rid and e["system"] != "Human"]
    human = [REVIEW for r in w.reviews if r["request"] == rid]
    return auto, human


def totals(w, rids: list[str]) -> dict:
    old = [s for r in rids for s in old_steps(w, r)]
    human = [s for r in rids for s in new_steps(w, r)[1]]
    auto = [e for r in rids for e in new_steps(w, r)[0]]
    customer_emails = sum(1 for r in rids if w.results[r]["email"])
    return {
        "old": {"people touches": len(old), "hands-on minutes": sum(s.minutes for s in old),
                "fields retyped": sum(s.fields for s in old), "emails written": sum(s.emails for s in old),
                "est. hours waiting": sum(s.waits for s in old) * WAIT_HOURS},
        "new": {"people touches": len(human), "hands-on minutes": sum(s.minutes for s in human),
                "fields retyped": 0, "emails written": 0,
                "est. hours waiting": len(human) * REVIEW_WAIT_HOURS},
        "automated actions": len(auto),
        "customer emails drafted": customer_emails,
    }


def account_of(w, rid: str) -> str | None:
    """CRM account a request ended up on (None for spam or anything never converted)."""
    res = w.results.get(rid)
    if not res:
        return None
    acct = (res.get("identity") or {}).get("account") or ""
    if acct:
        return acct.split()[0]
    lead = next((l for l in w.crm.leads if l["source"].endswith(f"({rid})") and l["converted_contact_id"]), None)
    if lead:
        return next(c["account_id"] for c in w.crm.contacts if c["id"] == lead["converted_contact_id"])
    return None


def journeys(w) -> dict[str, list[str]]:
    """Account id -> its requests in time order (one customer's sample-to-quote journey)."""
    out: dict[str, list[str]] = {}
    for r in sorted(w.inbox, key=lambda r: r["received"]):
        if (acct := account_of(w, r["id"])) is not None:
            out.setdefault(acct, []).append(r["id"])
    return out
