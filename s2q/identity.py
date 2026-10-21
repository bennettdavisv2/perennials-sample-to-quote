"""Who is this? Match an inbound request to existing CRM records before creating anything.

Order matters: exact email beats domain, domain beats company name. Duplicate leads are
the most common way this workflow goes wrong (e.g. WEB-003 is Dana Ruiz from a second
address at the same firm).
"""
from __future__ import annotations

import re

from .extract import is_free_email


def _n(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def resolve(crm, req: dict) -> dict:
    email, name, company = req["email"], req.get("name"), req.get("company")
    domain = email.split("@")[-1]

    c = crm.contact_by_email(email)
    if c:
        return {"match": "Existing contact (email)", "contact": c, "account": crm.account(c["account_id"]),
                "lead": None, "confidence": "high"}

    lead = crm.lead_by_email(email)
    if lead and lead["converted_contact_id"]:
        c = next(x for x in crm.contacts if x["id"] == lead["converted_contact_id"])
        return {"match": "Converted lead (email)", "contact": c, "account": crm.account(c["account_id"]),
                "lead": lead, "confidence": "high"}
    if lead:
        return {"match": "Existing open lead (email)", "contact": None, "account": None, "lead": lead,
                "confidence": "high"}

    if not is_free_email(email) and name:
        # A lead can wait hours for a rep; a second address from the same person must not open a second lead.
        for l in crm.leads:
            if (not l["converted_contact_id"] and l["status"] != "Disqualified" and _n(l["name"]) == _n(name)
                    and l["email"].split("@")[-1] == domain):
                return {"match": "Same person, new email address (open lead)", "contact": None, "account": None,
                        "lead": l, "confidence": "high"}

    if not is_free_email(email):
        same_domain = crm.contacts_by_domain(domain)
        for c in same_domain:
            if name and _n(c["name"]) == _n(name):
                return {"match": "Same person, new email address (domain + name)", "contact": c,
                        "account": crm.account(c["account_id"]), "lead": None, "confidence": "high"}
        if same_domain:
            c = same_domain[0]
            return {"match": "Same company (email domain)", "contact": None, "account": crm.account(c["account_id"]),
                    "lead": None, "confidence": "medium"}

    acct = crm.account_by_name(company)
    if acct:
        return {"match": "Same company (company name)", "contact": None, "account": acct, "lead": None,
                "confidence": "medium"}

    return {"match": "New", "contact": None, "account": None, "lead": None, "confidence": "n/a"}


def summary(ident: dict) -> dict:
    a = ident["account"]
    return {"match": ident["match"], "confidence": ident["confidence"],
            "account": f"{a['id']} {a['name']} ({a['type']}, {a['status']})" if a else "",
            "contact": f"{ident['contact']['id']} {ident['contact']['name']}" if ident["contact"] else "",
            "lead": ident["lead"]["id"] if ident["lead"] else ""}
