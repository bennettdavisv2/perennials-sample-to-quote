"""Mock CRM (stands in for Salesforce; HubSpot maps the same way).

Source of truth for: people and companies (leads, contacts, accounts), trade status,
qualification, opportunities, quotes sent to customers, and human-review tasks.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from ..audit import AuditLog

SF = "Salesforce REST: "


class MockCRM:
    def __init__(self, accounts: list[dict], contacts: list[dict], log: AuditLog):
        self.accounts = [dict(a) for a in accounts]
        self.contacts = [dict(c) for c in contacts]
        self.leads: list[dict] = []
        self.opportunities: list[dict] = []
        self.quotes: list[dict] = []
        self.tasks: list[dict] = []
        self.log = log
        self._seq = defaultdict(lambda: 100)

    def _id(self, prefix):
        self._seq[prefix] += 1
        return f"{prefix}-{self._seq[prefix]:04d}"

    # ---------- lookups ----------
    def account(self, account_id):
        return next((a for a in self.accounts if a["id"] == account_id), None)

    def contact_by_email(self, email):
        return next((c for c in self.contacts if c["email"] == email or email in c.get("alt_emails", [])), None)

    def contacts_by_domain(self, domain):
        return [c for c in self.contacts if c["email"].split("@")[-1] == domain]

    def lead_by_email(self, email):
        return next((l for l in self.leads if l["email"] == email), None)

    def account_by_name(self, name):
        n = _norm(name)
        return next((a for a in self.accounts if _norm(a["name"]) == n), None) if n else None

    # ---------- leads ----------
    def create_lead(self, req: dict, segment_hint: str, project: str) -> dict:
        lead = {"id": self._id("LEAD"), "name": req["name"] or "", "company": req["company"] or "",
                "email": req["email"], "source": f"{req['channel']} ({req['id']})", "project": project,
                "segment_hint": segment_hint, "status": "New", "status_reason": "",
                "converted_contact_id": None, "created": req["received"]}
        self.leads.append(lead)
        self.log.record("CRM", "Create lead", f"{lead['id']} {lead['name'] or lead['email']} via {req['id']}",
                        SF + "POST /sobjects/Lead (LeadSource = Web Sample Request)")
        return lead

    def set_lead_status(self, lead: dict, status: str, reason: str):
        lead["status"], lead["status_reason"] = status, reason
        self.log.record("CRM", "Update lead status", f"{lead['id']} -> {status}: {reason}",
                        SF + "PATCH /sobjects/Lead/{id} (Status, Qualification_Reason__c)")

    def convert_lead(self, lead: dict, account: dict | None, contact: dict | None,
                     new_account: dict | None = None) -> tuple[dict, dict]:
        """Convert a lead into (existing or new) account + contact, as Salesforce lead convert does."""
        if account is None:
            account = {"id": self._id("ACC"), "status": "Prospect", **(new_account or {})}
            self.accounts.append(account)
            self.log.record("CRM", "Create account", f"{account['id']} {account['name']} ({account['type']})",
                            SF + "Lead convert -> new Account")
        if contact is None:
            contact = {"id": self._id("CON"), "account_id": account["id"], "name": lead["name"],
                       "email": lead["email"], "alt_emails": []}
            self.contacts.append(contact)
            self.log.record("CRM", "Create contact", f"{contact['id']} {contact['name']} at {account['name']}",
                            SF + "Lead convert -> new Contact")
        lead["converted_contact_id"] = contact["id"]
        self.set_lead_status(lead, "Converted", f"to {account['id']} / {contact['id']}")
        return account, contact

    def add_alt_email(self, contact: dict, email: str):
        if email != contact["email"] and email not in contact["alt_emails"]:
            contact["alt_emails"].append(email)
            self.log.record("CRM", "Add alternate email", f"{contact['id']} += {email}",
                            SF + "PATCH /sobjects/Contact/{id} (Alternate_Email__c)")

    # ---------- opportunities ----------
    def open_opportunity(self, account_id: str) -> dict | None:
        opps = [o for o in self.opportunities if o["account_id"] == account_id and not o["stage"].startswith("Closed")]
        return opps[-1] if opps else None

    def create_opportunity(self, account: dict, contact: dict, name: str, stage: str, now: datetime) -> dict:
        opp = {"id": self._id("OPP"), "account_id": account["id"], "contact_id": contact["id"], "name": name,
               "stage": stage, "amount": 0.0, "sample_orders": [], "created": now}
        self.opportunities.append(opp)
        self.log.record("CRM", "Create opportunity", f"{opp['id']} '{name}' ({stage})",
                        SF + "POST /sobjects/Opportunity + OpportunityContactRole")
        return opp

    def update_opportunity(self, opp: dict, **fields):
        opp.update(fields)
        self.log.record("CRM", "Update opportunity", f"{opp['id']}: " + ", ".join(f"{k}={v}" for k, v in fields.items()),
                        SF + "PATCH /sobjects/Opportunity/{id}")

    # ---------- quotes ----------
    def open_quote(self, opp_id: str) -> dict | None:
        qs = [q for q in self.quotes if q["opp_id"] == opp_id and q["status"] not in ("Superseded", "Rejected")]
        return qs[-1] if qs else None

    def create_quote(self, opp: dict, lines: list[dict], total: float, flags: list[str], status: str,
                     now: datetime, valid_days: int, budgetary: bool, revision_of: dict | None) -> dict:
        number = revision_of["number"] if revision_of else self._id("Q")
        version = revision_of["version"] + 1 if revision_of else 1
        q = {"id": f"{number}-v{version}", "number": number, "version": version, "opp_id": opp["id"],
             "lines": lines, "total": total, "flags": flags, "status": status, "budgetary": budgetary,
             "created": now, "valid_until": now + timedelta(days=valid_days), "reservation_id": None}
        if revision_of:
            revision_of["status"] = "Superseded"
            self.log.record("CRM", "Supersede quote", f"{revision_of['id']} -> {q['id']}",
                            SF + "PATCH /sobjects/Quote/{id} (Status = Superseded)")
        self.quotes.append(q)
        self.log.record("CRM", "Create quote", f"{q['id']} on {opp['id']}: ${total:,.2f} [{status}]",
                        SF + "POST /sobjects/Quote + QuoteLineItem; PDF attached via ContentVersion")
        return q

    def set_quote_status(self, q: dict, status: str):
        q["status"] = status
        self.log.record("CRM", "Update quote", f"{q['id']} -> {status}", SF + "PATCH /sobjects/Quote/{id}")

    # ---------- human tasks ----------
    def create_task(self, subject: str, related_to: str, owner: str = "Sales rep") -> dict:
        t = {"id": self._id("TASK"), "subject": subject, "related_to": related_to, "owner": owner, "status": "Open"}
        self.tasks.append(t)
        self.log.record("CRM", "Create review task", f"{t['id']} for {owner}: {subject}",
                        SF + "POST /sobjects/Task (assigned via queue / Flow)")
        return t


def _norm(s):
    import re
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())
