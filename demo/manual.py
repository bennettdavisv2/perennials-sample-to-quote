"""Today's process, by hand: the state behind the demo's "Today (manual)" page.

No workflow and no integration. The CSR reads a website notification email, then types everything into
a blank Salesforce and a blank NetSuite and writes every email to the customer and to order ops
themselves. The desk counts what that costs as it happens: values typed by hand, emails written,
switches between systems, and elapsed time. These are measured during the run, not estimated.

It starts from the same day-one data as the new system's clean start (demo/seed.py): NetSuite's items,
dye lots and price rules and Salesforce's existing accounts and contacts.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from s2q.data import DEFAULT_DATA, load_workbook
from s2q.pricing import price_line, to_yards

QUOTES = "quotes@perennialsfabrics.com"   # the shared inbox the CSR works from
ORDERS = "orders@perennialsfabrics.com"   # order ops, who key NetSuite orders from the rep's email
WEBSITE = "website@perennialsfabrics.com" # the form-notification sender
CSR_SYSTEMS = ("Gmail", "Salesforce", "NetSuite")


def filled(*values) -> int:
    """How many of these form values were actually entered (blank text and zero numbers don't count)."""
    return sum(1 for v in values if v not in (None, "", 0, 0.0, []) and str(v).strip())


@dataclass
class Desk:
    accounts: list[dict]
    contacts: list[dict]
    lots: list[dict]
    pricing: object
    leads: list[dict] = field(default_factory=list)
    opportunities: list[dict] = field(default_factory=list)
    quotes: list[dict] = field(default_factory=list)
    customers: list[dict] = field(default_factory=list)   # NetSuite
    orders: list[dict] = field(default_factory=list)      # NetSuite sales orders (sample / hold)
    emails: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)      # everything that happened, in order
    typed: int = 0
    emails_written: int = 0
    switches: int = 0
    system: str = "Gmail"
    started: float | None = None
    last: float | None = None
    stopped: float | None = None

    @classmethod
    def new(cls, data_path=DEFAULT_DATA) -> "Desk":
        d = load_workbook(data_path)
        return cls([dict(a) for a in d["accounts"]], [dict(c) for c in d["contacts"]],
                   [dict(l) for l in d["lots"]], d["pricing"])

    # ------------------------------------------------------------------ bookkeeping
    def _event(self, kind: str, detail: str, by_csr: bool = True, **extra) -> dict:
        now = time.time()
        if by_csr:
            self.started = self.started or now
            self.last = now
        e = {"seq": len(self.events), "kind": kind, "detail": detail, "csr": by_csr, "t": now, **extra}
        self.events.append(e)
        return e

    def _id(self, prefix: str, rows: list) -> str:
        return f"{prefix}-{len(rows) + 1:04d}"

    def elapsed(self) -> float:
        """Seconds since the CSR's first action: live until the clock is stopped."""
        if not self.started:
            return 0.0
        return (self.stopped or time.time()) - self.started

    def stop(self):
        self.stopped = self.stopped or (self.last or time.time())

    def switch(self, system: str):
        if system != self.system and system in CSR_SYSTEMS:
            self.switches += 1
            self._event("switch", f"{self.system} -> {system}")
        self.system = system

    def type(self, n: int):
        self.typed += n

    # ------------------------------------------------------------------ the customer (Dana) side
    def web_sample_request(self, name, company, email, skus: list[str], project_type, project_name="", note=""):
        lines = "\n".join(f"  - {self.item_label(s)}" for s in skus)
        body = (f"New sample request from the website.\n\nName: {name}\nCompany: {company}\nEmail: {email}\n"
                f"Project type: {project_type}\nProject: {project_name}\n\nSamples:\n{lines}\n\nNote: {note}")
        self._mail(WEBSITE, QUOTES, f"[Website] Sample request from {name}", body, by_csr=False)
        self._event("web_sample", f"{name}: {', '.join(skus)}", by_csr=False, email=email.strip().lower())

    def web_quote_request(self, name, company, email, sku, length, unit, cfa, project_name, date_needed=None,
                          note=""):
        body = (f"New quote request from the website.\n\nName: {name}\nCompany: {company}\nEmail: {email}\n"
                f"Project: {project_name}\n\nFabric: {self.item_label(sku)}\nLength: {length:g} {unit}\n"
                f"CFA: {cfa}\nDate needed: {date_needed or 'not given'}\n\nComment: {note}")
        self._mail(WEBSITE, QUOTES, f"[Website] Quote request from {name}", body, by_csr=False)
        self._event("web_quote", f"{name}: {length:g} {unit} of {sku}", by_csr=False, email=email.strip().lower())

    def customer_email(self, frm, subject, body):
        self._mail(frm, QUOTES, subject, body, by_csr=False)
        self._event("customer_email", subject, by_csr=False)

    # ------------------------------------------------------------------ Gmail (the CSR and order ops)
    def _mail(self, frm, to, subject, body, by_csr=True):
        m = {"id": len(self.emails) + 1, "from": frm, "to": to.strip().lower(), "subject": subject, "body": body,
             "seq": len(self.events)}
        self.emails.append(m)
        return m

    def send(self, frm, to, subject, body):
        """An email the CSR (or order ops) writes by hand."""
        m = self._mail(frm, to, subject, body)
        self.emails_written += 1
        self._event("email", f"{frm} -> {to}: {subject}", to=m["to"])
        return m

    def mailbox(self, address: str) -> list[dict]:
        address = address.lower()
        return [m for m in reversed(self.emails) if m["to"] == address or m["from"].lower() == address]

    # ------------------------------------------------------------------ Salesforce
    def search(self, text: str) -> list[dict]:
        """Global search: what a CSR runs first to see whether the customer already exists."""
        self.type(filled(text))
        self._event("sf_search", text)
        t = text.strip().lower()
        if not t:
            return []
        hits = [{"type": "Account", "id": a["id"], "name": a["name"], "detail": a["type"]}
                for a in self.accounts if t in a["name"].lower()]
        hits += [{"type": "Contact", "id": c["id"], "name": c["name"], "detail": c["email"]}
                 for c in self.contacts if t in c["name"].lower() or t in c["email"].lower()]
        hits += [{"type": "Lead", "id": l["id"], "name": l["name"], "detail": l["email"]}
                 for l in self.leads if t in l["name"].lower() or t in l["email"].lower()]
        return hits

    def create_lead(self, name, company, email, source, project, description, status):
        lead = {"id": self._id("LEAD", self.leads), "name": name, "company": company, "email": email.strip().lower(),
                "source": source, "project": project, "description": description, "status": status}
        self.leads.append(lead)
        self.type(filled(name, company, email, source, project, description, status))
        self._event("sf_lead", f"{lead['id']} {name}")
        return lead

    def convert_lead(self, lead_id, account_name, account_type, contact_name, contact_email):
        """Salesforce's Convert: the CSR confirms (and often fixes) the account and contact fields."""
        lead = next(l for l in self.leads if l["id"] == lead_id)
        acct = next((a for a in self.accounts if a["name"].lower() == account_name.strip().lower()), None)
        if acct is None:
            acct = {"id": f"ACC-{len(self.accounts) + 101:04d}", "name": account_name.strip(), "type": account_type,
                    "status": "Prospect"}
            self.accounts.append(acct)
        con = {"id": f"CON-{len(self.contacts) + 101:04d}", "account_id": acct["id"], "name": contact_name,
               "email": contact_email.strip().lower(), "alt_emails": []}
        self.contacts.append(con)
        lead["status"], lead["converted_to"] = "Converted", con["id"]
        self.type(filled(account_name, account_type, contact_name, contact_email))
        self._event("sf_convert", f"{lead_id} -> {acct['id']} / {con['id']}")
        return acct, con

    def create_opportunity(self, name, account_id, contact_id, stage, close_date, amount=0.0):
        opp = {"id": self._id("OPP", self.opportunities), "name": name, "account_id": account_id,
               "contact_id": contact_id, "stage": stage, "close_date": close_date, "amount": amount}
        self.opportunities.append(opp)
        self.type(filled(name, account_id, contact_id, stage, close_date, amount))
        self._event("sf_opp", f"{opp['id']} {name}")
        return opp

    def create_quote(self, opp_id, lines: list[dict], total: float, valid_until=None):
        """lines: [{sku, description, yards, unit_price, line_total}], all typed by the CSR."""
        lines = [l for l in lines if filled(l.get("sku"))]
        prior = [q for q in self.quotes if q["opp_id"] == opp_id and q["status"] != "Superseded"]
        for q in prior:
            q["status"] = "Superseded"
        q = {"id": f"Q-{len(self.quotes) + 1:04d}", "opp_id": opp_id, "lines": lines, "total": total,
             "valid_until": valid_until, "status": "Draft"}
        self.quotes.append(q)
        self.type(filled(opp_id, total, valid_until) + sum(filled(*l.values()) for l in lines))
        self._event("sf_quote", f"{q['id']} ${total:,.2f}")
        return q

    def check_quote(self, q: dict) -> dict:
        """What the price rules say the quote should have been: catches arithmetic and discount mistakes."""
        right, wrong = 0.0, []
        for l in q["lines"]:
            item = self.item(l["sku"])
            if not item or not l.get("yards"):
                wrong.append(f"{l['sku']}: not a NetSuite item" if not item else f"{l['sku']}: no yardage")
                continue
            p = price_line(item["list_price"], to_yards(l["yards"], "yd"), True, self.pricing)
            right += p["line_total"]
            if abs((l.get("line_total") or 0) - p["line_total"]) > 0.005:
                wrong.append(f"{l['sku']}: typed ${l.get('line_total') or 0:,.2f}, rules give ${p['line_total']:,.2f}")
        right = round(right, 2)
        if abs(q["total"] - right) > 0.005:
            wrong.append(f"Total: typed ${q['total']:,.2f}, rules give ${right:,.2f}")
        return {"expected": right, "problems": wrong}

    # ------------------------------------------------------------------ NetSuite
    def item(self, sku: str) -> dict | None:
        lots = [l for l in self.lots if l["sku"] == sku.strip().upper()]
        return lots[0] if lots else None

    def item_label(self, sku: str) -> str:
        it = self.item(sku)
        return f"{it['fabric']} - {it['color']} ({it['sku']})" if it else sku

    def lookup(self, text: str) -> list[dict]:
        """Inventory search by SKU, fabric or color."""
        self.type(filled(text))
        self._event("ns_lookup", text)
        t = text.strip().lower()
        return [l for l in self.lots if t in f"{l['sku']} {l['fabric']} {l['color']}".lower()] if t else []

    def create_customer(self, name, email, sf_account, price_level, terms):
        c = {"id": self._id("CUST", self.customers), "name": name, "email": email, "sf_account": sf_account,
             "price_level": price_level, "terms": terms}
        self.customers.append(c)
        self.type(filled(name, email, sf_account, price_level, terms))
        self._event("ns_customer", f"{c['id']} {name}")
        return c

    def create_order(self, form, customer_id, memo, lines: list[dict], ship_to=""):
        """form: 'Sample' (memo swatches) or 'Pending hold' (reserves yardage on the dye lots typed in).
        lines: [{sku, lot, qty}]. Lines that don't match a SKU + lot in NetSuite come back as errors."""
        lines = [l for l in lines if filled(l.get("sku"))]
        errors = []
        for l in lines:
            l["sku"] = l["sku"].strip().upper()
            if not self.item(l["sku"]):
                errors.append(f"{l['sku']} is not a NetSuite item")
            elif form == "Pending hold":
                want = (l.get("lot") or "").strip().upper()
                lot = next((x for x in self.lots if x["sku"] == l["sku"] and x["lot"] == want), None)
                if not lot:
                    errors.append(f"{l['sku']}: no dye lot {l.get('lot') or '(blank)'}")
                elif lot["on_hand"] - lot["reserved"] < (l.get("qty") or 0):
                    free = lot["on_hand"] - lot["reserved"]
                    errors.append(f"{l['sku']} lot {lot['lot']}: only {free:g} yd available")
        self.type(filled(form, customer_id, memo, ship_to) + sum(filled(*l.values()) for l in lines))
        if errors or not lines:
            self._event("ns_error", "; ".join(errors) or "no lines")
            return None, errors or ["Add at least one line"]
        if form == "Pending hold":
            for l in lines:
                l["lot"] = l["lot"].strip().upper()
                next(x for x in self.lots if x["sku"] == l["sku"] and x["lot"] == l["lot"])["reserved"] += l["qty"]
        so = {"id": self._id("SO" if form == "Pending hold" else "SMP", [o for o in self.orders if o["form"] == form]),
              "form": form, "customer": customer_id, "memo": memo, "lines": lines, "ship_to": ship_to,
              "status": "Pending Approval (hold)" if form == "Pending hold" else "Pending Fulfillment"}
        self.orders.append(so)
        self._event("ns_order", f"{so['id']} {form}")
        return so, []

    def release(self, so_id: str):
        so = next(o for o in self.orders if o["id"] == so_id)
        if so["status"].startswith("Released"):
            return
        for l in so["lines"]:
            next(x for x in self.lots if x["sku"] == l["sku"] and x["lot"] == l["lot"])["reserved"] -= l["qty"]
        so["status"] = "Released"
        self.type(1)
        self._event("ns_release", so_id)

    # ------------------------------------------------------------------ progress
    def _first(self, kind: str, after: int = -1, pred=lambda e: True) -> dict | None:
        return next((e for e in self.events if e["kind"] == kind and e["seq"] > after and pred(e)), None)

    def checklist(self) -> list[tuple[str, str, bool]]:
        """(section, step, done) for today's process, in the order a CSR does it."""
        web = next((e for e in self.events if e.get("email")), {})
        to_cust = lambda e: e.get("to") == web.get("email")  # noqa: E731
        to_ops = lambda e: e.get("to") == ORDERS  # noqa: E731
        seq = lambda e: e["seq"] if e else 10**9  # noqa: E731
        sample = self._first("web_sample")
        smp = self._first("ns_order", pred=lambda e: "Sample" in e["detail"])
        quote_req = self._first("web_quote")
        q1 = self._first("sf_quote", after=seq(quote_req))
        change = self._first("customer_email", after=seq(q1))
        q2 = self._first("sf_quote", after=seq(change))
        hold2 = self._first("ns_order", after=seq(change), pred=lambda e: "hold" in e["detail"])
        steps = [
            ("Samples", "Dana requests samples on the website (customer)", sample),
            ("Samples", "Search Salesforce: is she already a customer?", self._first("sf_search", after=seq(sample))),
            ("Samples", "Create the lead", self._first("sf_lead")),
            ("Samples", "Qualify her and convert: Account + Contact", self._first("sf_convert")),
            ("Samples", "Create the opportunity", self._first("sf_opp")),
            ("Samples", "Email order ops the sample request", self._first("email", after=seq(sample), pred=to_ops)),
            ("Samples", "Create the NetSuite customer", self._first("ns_customer")),
            ("Samples", "Enter the sample order in NetSuite", smp),
            ("Samples", "Email Dana that samples are on the way", self._first("email", after=seq(smp), pred=to_cust)),
            ("Quote", "Dana requests a quote on the website (customer)", quote_req),
            ("Quote", "Reply: 'checking stock and pricing'", self._first("email", after=seq(quote_req), pred=to_cust)),
            ("Quote", "Look up stock by dye lot and list price in NetSuite",
             self._first("ns_lookup", after=seq(quote_req))),
            ("Quote", "Email order ops to hold the yardage", self._first("email", after=seq(quote_req), pred=to_ops)),
            ("Quote", "Enter the hold in NetSuite (pending sales order)",
             self._first("ns_order", after=seq(quote_req), pred=lambda e: "hold" in e["detail"])),
            ("Quote", "Work out the price and build the quote in Salesforce", q1),
            ("Quote", "Email Dana the quote", self._first("email", after=seq(q1), pred=to_cust)),
            ("Change", "Dana emails a change (customer)", change),
            ("Change", "Release the old hold in NetSuite", self._first("ns_release", after=seq(change))),
            ("Change", "Enter the new hold", hold2),
            ("Change", "Revise the quote in Salesforce", q2),
            ("Change", "Email Dana the revised quote", self._first("email", after=seq(q2), pred=to_cust)),
        ]
        return [(sec, step, e is not None) for sec, step, e in steps]

    def summary(self) -> dict:
        return {"elapsed_s": self.elapsed(), "typed": self.typed, "emails": self.emails_written,
                "switches": self.switches, "records": len(self.leads) + len(self.opportunities) + len(self.quotes)
                + len(self.customers) + len(self.orders) + sum(1 for l in self.leads if l["status"] == "Converted") * 2,
                "steps_done": sum(1 for _, s, d in self.checklist() if d and "(customer)" not in s)}
