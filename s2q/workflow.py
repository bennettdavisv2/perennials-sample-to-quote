"""Sample-to-quote orchestrator.

One `process()` call takes an inbound request through the six stages:

  1 Sample request        Website -> CRM   create Lead (after spam filter + dedupe)
  2 Lead qualification    CRM              policy table in qualify.py
  3 Sample order + Opp    ERP + CRM        convert lead, Opportunity, ERP sample order
  4 Quote request         Email -> CRM     match sender, find Opportunity
  5 Price quote           ERP -> CRM       ERP prices lines, CRM stores Quote
  6 Inventory reservation ERP              pending sales order against dye lots

Anything the policy is not sure about becomes a Review item (and a CRM Task) instead
of a silent guess. Approving a review item runs the deferred action.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from . import emails, identity, qualify
from .adapters import MockCRM, MockERP
from .audit import AuditLog
from .data import DEFAULT_DATA, load_workbook
from .extract import Extractor
from .pricing import to_yards

STAGES = {1: "Sample request", 2: "Lead qualification", 3: "Sample order + Opportunity",
          4: "Quote request", 5: "Price quote", 6: "Inventory reservation"}
HIGH_VALUE = 20_000  # quotes above this need a manager's eye


class Workflow:
    def __init__(self, data_path: str | Path = DEFAULT_DATA, mode: str = "auto"):
        d = load_workbook(data_path)
        self.log = AuditLog()
        self.crm = MockCRM(d["accounts"], d["contacts"], self.log)
        self.erp = MockERP(d["lots"], d["pricing"], self.log)
        self.cfg = d["pricing"]
        self.inbox = d["requests"]
        self.extractor = Extractor(self.erp.items(), mode)
        self.results: dict[str, dict] = {}
        self.reviews: list[dict] = []
        self._seq = defaultdict(int)

    # ------------------------------------------------------------------ driver
    def pending(self):
        return [r for r in self.inbox if r["id"] not in self.results]

    def process_next(self):
        p = self.pending()
        return self.process(p[0]) if p else None

    def process_all(self):
        while self.pending():
            self.process_next()

    def submit(self, req: dict) -> dict:
        """A live request (demo storefront checkout or the quotes@ inbox) joins the inbox and runs now."""
        self.inbox.append(req)
        return self.process(req)

    def process(self, req: dict) -> dict:
        self.log.current_request, self.log.clock = req["id"], req["received"]
        src = "Website" if req["channel"].lower().startswith("website") else "Email"
        self.log.record(src, "Inbound received", f"{req['type']} from {req['email']}",
                        "WooCommerce form webhook" if src == "Website" else "Shared inbox -> email-to-case / Gmail API")
        ext, notes = self.extractor.extract(req)
        self.log.record("AI", "Extract request", f"{ext['method']}: segment={ext['segment_hint']}, "
                        f"items={[i['skus'] for i in ext['items']]}", "Claude API (tool-use JSON) or rules fallback")
        res = {"request": req, "extraction": ext, "extract_notes": notes, "stages": {}, "flags": [],
               "email": None, "outcome": "", "identity": None, "qualification": None}
        self.results[req["id"]] = res
        if req["type"].lower().startswith("sample"):
            self._sample_request(res)
        else:
            self._quote_request(res)
        return res

    # ------------------------------------------------------------------ helpers
    def _stage(self, res, n, status, summary):
        res["stages"][n] = {"stage": STAGES[n], "status": status, "summary": summary}

    def _review(self, res, stage, reason, proposed, action, payload, owner="Sales rep", message=None):
        self._seq["REV"] += 1
        rid = f"REV-{self._seq['REV']:03d}"
        task = self.crm.create_task(f"[{rid}] {reason}", res["request"]["id"], owner)
        item = {"id": rid, "request": res["request"]["id"], "stage": stage, "reason": reason,
                "proposed": proposed, "action": action, "payload": payload, "status": "Open",
                "owner": owner, "task_id": task["id"],
                "message": message,  # drafted customer email, so the rep's next step is one click, not a thread
                "asked": False}
        self.reviews.append(item)
        return item

    def _sampled_skus(self, erp_customer: str) -> set[str]:
        return {l["sku"] for so in self.erp.sales_orders if so["type"] == "Sample" and so["customer"] == erp_customer
                for l in so["lines"]}

    def _items_desc(self, ext: dict) -> list[str]:
        return [self._sku_desc(s) for it in ext["items"] for s in it["skus"] if self.erp.get_item(s)]

    def _sku_desc(self, sku):
        it = self.erp.get_item(sku)
        return f"{it['fabric']} - {it['color']} ({sku})"

    # ------------------------------------------------------------------ stages 1-3
    def _sample_request(self, res):
        req, ext = res["request"], res["extraction"]
        ident = identity.resolve(self.crm, req)
        res["identity"] = identity.summary(ident)
        q = qualify.decide(ext, ident, req)
        res["qualification"] = q

        # Stage 1: Website -> CRM
        if q["decision"] == "spam":
            self.log.record("Website", "Spam filtered", "No CRM record created", "Form spam filter / reCAPTCHA + Akismet")
            self._stage(res, 1, "blocked", "Spam: filtered at the website, nothing written to CRM")
            self._stage(res, 2, "n/a", "")
            self._stage(res, 3, "n/a", "")
            res["outcome"] = "Spam filtered"
            return
        lead = ident["lead"] or self.crm.create_lead(req, ext["segment_hint"], ext.get("project", ""))
        res["lead_id"] = lead["id"]
        self._stage(res, 1, "done", f"Lead {lead['id']} ({ident['match']})")

        # Stage 2: qualification
        d = q["decision"]
        if d == "disqualified":
            self.crm.set_lead_status(lead, "Disqualified", "; ".join(q["reasons"]))
            self._stage(res, 2, "done", "Disqualified: " + "; ".join(q["reasons"]))
            self._stage(res, 3, "skipped", "No samples or price list for Do Not Sell accounts")
            res["flags"].append("Do Not Sell account asked for samples and a trade price list: account owner notified")
            self.crm.create_task(f"FYI: {ident['account']['name']} (Do Not Sell) requested samples/price list via {req['id']}",
                                 req["id"], "Account owner")
            res["outcome"] = "Disqualified (Do Not Sell)"
            return
        if d == "non_trade":
            self.crm.set_lead_status(lead, "Nurture - Non-trade", "; ".join(q["reasons"]))
            self._stage(res, 2, "done", "Non-trade: " + "; ".join(q["reasons"]))
            self._stage(res, 3, "skipped", "Free samples are for qualified trade leads")
            res["email"] = emails.non_trade_reply(req["name"], ext["wildcard"])
            res["outcome"] = "Non-trade: nurture email, no free samples"
            return
        if d == "review":
            self.crm.set_lead_status(lead, "Needs Review", "; ".join(q["reasons"]))
            self._stage(res, 2, "review", "; ".join(q["reasons"]))
            self._stage(res, 3, "waiting", "Waiting on qualification review")
            self._review(res, "Lead qualification", "; ".join(q["reasons"]),
                         "Qualify as trade and send requested samples", "qualify_and_sample", {"lead_id": lead["id"]},
                         message=emails.trade_verification(req["name"], self._items_desc(ext)))
            res["outcome"] = "Needs review: qualification"
            return

        self.crm.set_lead_status(lead, "Qualified", "; ".join(q["reasons"]))
        self._stage(res, 2, "done", "Qualified trade: " + "; ".join(q["reasons"]))
        self._place_samples(res, lead, ident)

    def _place_samples(self, res, lead, ident, approved_cap=False):
        req, ext = res["request"], res["extraction"]
        acct_type = f"Trade - {ext.get('trade_subtype') or 'Other'}".replace(" - ", " – ")
        account, contact = self.crm.convert_lead(
            lead, ident["account"], ident["contact"],
            new_account={"name": req["company"] or f"{req['name']} (independent)", "type": acct_type})
        if ident["match"].startswith("Same person"):
            self.crm.add_alt_email(contact, req["email"])
        cust = self.erp.upsert_customer(account)

        opp = self.crm.open_opportunity(account["id"])
        if opp:
            note = f"added to open opportunity {opp['id']}"
        else:
            proj = (ext.get("project") or "").strip()
            opp = self.crm.create_opportunity(account, contact, f"{account['name']} - {proj or 'New project'}",
                                              "Sampling", req["received"])
            note = f"new opportunity {opp['id']}"

        # Which SKUs can be sampled?
        skus, excluded, notes = [], [], []
        res["flags"] += [f"Cart line {s} is not an item in the ERP: left out" for s in ext.get("invalid_skus", [])]
        for it in ext["items"]:
            if it["ambiguous"]:
                res["flags"].append(f"'{it['reference']}' is ambiguous: sending all colors {it['skus']}")
            for sku in it["skus"]:
                item = self.erp.get_item(sku)
                if item["status"] == "Discontinued":
                    excluded.append(f"{self._sku_desc(sku)}: discontinued, no new samples. "
                                    f"{item['available']:.0f} yd remain if you'd like a quote")
                    res["flags"].append(f"{sku} discontinued: excluded from samples")
                    continue
                if item["status"].startswith("Backorder"):
                    notes.append(f"Note: {self._sku_desc(sku)} yardage is on backorder ({item['status']}).")
                elif item["available"] <= 0:
                    notes.append(f"Note: {self._sku_desc(sku)} yardage is currently out of stock.")
                if sku not in skus:
                    skus.append(sku)

        if ext["wildcard"] and not approved_cap:
            self._stage(res, 3, "review", f"Opportunity: {note}. Request asks for 'everything': rep to narrow down")
            self._review(res, "Sample order", "Open-ended sample request",
                         f"Send the first {self.cfg.max_samples} and ask the customer to narrow the list",
                         "place_samples_capped", {"lead_id": lead["id"]},
                         message=emails.sample_pick(req["name"], [], self.cfg.max_samples))
            res["outcome"] = "Needs review: open-ended request"
            return
        if len(skus) > self.cfg.max_samples and not approved_cap:
            self._stage(res, 3, "review", f"Opportunity: {note}. {len(skus)} SKUs requested, max {self.cfg.max_samples}")
            self._review(res, "Sample order", f"{len(skus)} samples requested (max {self.cfg.max_samples})",
                         f"Send first {self.cfg.max_samples} as listed and offer the rest as a follow-up",
                         "place_samples_capped", {"lead_id": lead["id"]},
                         message=emails.sample_pick(req["name"], [self._sku_desc(s) for s in skus], self.cfg.max_samples))
            res["outcome"] = "Needs review: over sample limit"
            return
        if len(skus) > self.cfg.max_samples:
            extra = skus[self.cfg.max_samples:]
            skus = skus[: self.cfg.max_samples]
            excluded += [f"{self._sku_desc(s)}: over the {self.cfg.max_samples}-sample limit, we'll follow up" for s in extra]

        if skus:
            so = self.erp.create_sample_order(cust, skus, req["email"], req["received"])
            opp["sample_orders"].append(so["id"])
            self.crm.update_opportunity(opp, sample_orders=list(opp["sample_orders"]))
            self._stage(res, 3, "done", f"{so['id']} ({len(skus)} samples); {note}")
            res["outcome"] = f"Samples sent ({len(skus)})"
        else:
            self._stage(res, 3, "done", f"No eligible samples; {note}")
            res["outcome"] = "Qualified, no eligible samples"
        res["email"] = emails.sample_confirmation(req["name"], [self._sku_desc(s) for s in skus], excluded, notes, opp["name"])

    # ------------------------------------------------------------------ stages 4-6
    def _quote_request(self, res):
        req, ext = res["request"], res["extraction"]
        for n in (1, 2, 3):
            self._stage(res, n, "n/a", "")
        ident = identity.resolve(self.crm, req)
        res["identity"] = identity.summary(ident)
        q = qualify.decide(ext, ident, req)
        res["qualification"] = q

        if q["decision"] in ("spam", "disqualified"):
            self._stage(res, 4, "blocked", "; ".join(q["reasons"]))
            res["outcome"] = f"Blocked ({q['decision']})"
            return

        account, contact = ident["account"], ident["contact"]
        if contact is None:
            lead = ident["lead"] or self.crm.create_lead(req, ext["segment_hint"], ext.get("project", ""))
            if q["decision"] == "review":
                self.crm.set_lead_status(lead, "Needs Review", "; ".join(q["reasons"]))
                self._stage(res, 4, "review", "Unknown sender; qualify before quoting")
                res["email"] = emails.trade_verification(req["name"], self._items_desc(ext), quote=True)
                self._review(res, "Quote request", "; ".join(q["reasons"]),
                             "Send the drafted question, then quote once they're verified", "send_question", {},
                             message=res["email"])
                res["outcome"] = "Needs review: unknown sender"
                return
            if q["decision"] == "non_trade":
                new_acct = {"name": f"{req['name']} (consumer)", "type": "Consumer / Retail"}
            else:
                new_acct = {"name": req["company"] or req["name"], "type": f"Trade – {ext.get('trade_subtype') or 'Other'}"}
            account, contact = self.crm.convert_lead(lead, account, None, new_account=new_acct)
        cust = self.erp.upsert_customer(account)

        opp = self.crm.open_opportunity(account["id"])
        if opp:
            opp_note = f"attached to {opp['id']} '{opp['name']}'"
        else:
            opp = self.crm.create_opportunity(account, contact, f"{account['name']} - {req['id']} quote", "Quoting",
                                              req["received"])
            opp_note = f"new opportunity {opp['id']}"
        self._stage(res, 4, "done", f"{ident['match']}; {opp_note}")

        # ---- Stage 5: price
        # A follow-up on the same opportunity that touches the same SKUs (or says "update") revises
        # the open quote. Release the old hold first so availability is computed correctly.
        prior = self.crm.open_quote(opp["id"])
        req_skus = {s for it in ext["items"] for s in it["skus"]}
        revision_of = None
        if prior and (ext.get("revision") or {l["sku"] for l in prior["lines"]} & req_skus):
            revision_of = prior
            if prior.get("reservation_id"):
                self.erp.release_reservation(prior["reservation_id"], f"superseded by revision of {prior['number']}")
        is_trade = str(account["type"]).startswith("Trade")
        flags = list(res["flags"])
        flags += [n for n in res["extract_notes"] if "disagree" in n]
        flags += [f"Cart line {s} is not an item in the ERP: not quoted" for s in ext.get("invalid_skus", [])]
        lines, line_desc, cust_notes, alloc_plan, questions = [], [], [], [], []
        sampled = self._sampled_skus(cust)
        for it in ext["items"]:
            skus = it["skus"]
            if len(skus) > 1:
                # Several colorways fit ("the canvas"). What we sampled to this customer usually settles it.
                hit = [s for s in skus if s in sampled]
                if len(hit) == 1:
                    skus = hit
                    cust_notes.append(f"Quoted in {self.erp.get_item(hit[0])['color']}, the colorway we sampled to you.")
                else:
                    why = "sampled more than one of them" if hit else "no sample history to go on"
                    opts = " or ".join(f"{i['color']} ({i['available']:g} yd in stock)" for i in map(self.erp.get_item, skus))
                    flags.append(f"'{it['reference']}' could be {skus} ({why}): drafted a question to the customer")
                    questions.append(f"Which {self.erp.get_item(skus[0])['fabric']} did you mean: {opts}?")
                    continue
            sku = skus[0]
            item = self.erp.get_item(sku)
            if it["quantity"] is None:
                flags.append(f"No quantity for {self._sku_desc(sku)}: drafted a question to the customer")
                questions.append(f"How much {item['fabric']} in {item['color']} do you need? "
                                 "Yards, feet or meters are all fine.")
                continue
            yards = to_yards(it["quantity"], it["unit"])
            converted = it["unit"] in ("m", "ft")
            conv = f" ({it['quantity']:g} {it['unit']} converted)" if converted else ""
            if converted:
                cust_notes.append(f"{it['quantity']:g} {it['unit']} quoted as {yards:g} yd (rounded up to the nearest 1/4 yd).")
            if it.get("needs_confirm"):  # e.g. the LLM named a SKU that doesn't exist
                flags.append(f"'{it['reference']}' interpreted as {self._sku_desc(sku)}: confirm with customer")
            if it.get("inferred"):
                # Only one catalog SKU fits ("green velvet" = Velvet Plush Moss): quote it, no hold. Naming it
                # in the email lets the customer catch a mistake without an extra round trip.
                cust_notes.append(f"We read '{it['reference']}' as {item['fabric']} in {item['color']}.")

            quote_yards, reserve = yards, True
            alloc = self.erp.allocate(sku, yards)
            if item["status"] == "Discontinued":
                if alloc["available"] < yards:
                    quote_yards = alloc["available"]
                    flags.append(f"{sku} discontinued: only {alloc['available']:g} yd left, quoted remaining stock")
                    cust_notes.append(f"{item['fabric']} {item['color']} is discontinued; {alloc['available']:g} yd remain.")
                alloc = self.erp.allocate(sku, quote_yards)
            elif item["status"].startswith("Backorder") or alloc["available"] <= 0:
                reserve = False
                eta = item["status"] if item["status"].startswith("Backorder") else "no stock on hand; ETA needed from purchasing"
                urgent = " Customer says ASAP." if ext.get("urgent") else ""
                flags.append(f"{sku} not available ({eta}); priced, not reserved.{urgent}")
                cust_notes.append(f"{item['fabric']} {item['color']}: not currently in stock ({eta.replace('Backorder – ', 'expected ')}).")
            else:
                if alloc["short"] > 0:
                    held = "budgetary, nothing reserved" if ext.get("budgetary") else "reserved what's available"
                    flags.append(f"{sku}: {yards:g} yd requested, {alloc['available']:g} yd available "
                                 f"({alloc['short']:g} yd short); {held}")
                    cust_notes.append(f"{item['fabric']} {item['color']}: {alloc['available']:g} yd available now; "
                                      f"we're confirming lead time for the remaining {alloc['short']:g} yd.")
                if alloc["split"]:
                    lots = ", ".join(f"{a['lot']} ({a['yards']:g} yd)" for a in alloc["lines"])
                    flags.append(f"{sku}: no single dye lot covers {yards:g} yd; split across {lots}. Needs a CFA (cutting for approval) from each lot")
                    cust_notes.append(f"{item['fabric']} {item['color']} would ship from more than one dye lot; "
                                      "we'll send a CFA (cutting for approval) from each lot.")
            p = self.erp.price(sku, quote_yards, is_trade)
            lines.append({"sku": sku, "description": f"{item['fabric']} - {item['color']}", **p,
                          "requested_yards": yards, "status": item["status"]})
            disc = f"{p['total_discount']*100:.0f}% off" if p["total_discount"] else "at"
            fee = f" + ${p['cut_fee']:.0f} cut fee" if p["cut_fee"] else ""
            line_desc.append(f"{item['fabric']} {item['color']} ({sku}): {quote_yards:g} yd{conv} x ${p['unit_price']:.2f}/yd "
                             f"({disc} ${p['list_price']:.0f} list){fee} = ${p['line_total']:,.2f}")
            if reserve and not ext.get("budgetary"):
                got = [a for a in alloc["lines"] if a["yards"] > 0]
                if got:
                    alloc_plan.append({"sku": sku, "allocation": got})

        total = round(sum(l["line_total"] for l in lines), 2)
        if total > HIGH_VALUE:
            flags.append(f"High-value quote (${total:,.0f} > ${HIGH_VALUE:,}): manager approval")
        if ext.get("need_by"):
            flags.append(f"Customer needs delivery {ext['need_by']}: confirm ship date")
        cust_notes += questions
        if not lines:
            self._stage(res, 5, "review", "Nothing could be priced: " + "; ".join(flags))
            self._stage(res, 6, "n/a", "")
            if questions:
                res["email"] = emails.clarifying_question(req["name"], questions)
            self._review(res, "Price quote", "; ".join(flags),
                         "Send the drafted question to the customer" if questions else "Clarify with customer",
                         "send_question" if questions else "none", {}, message=res["email"])
            res["flags"] = flags
            res["outcome"] = "Needs review: nothing priceable"
            return

        status = "Pending rep review" if flags else "Sent"
        quote = self.crm.create_quote(opp, lines, total, flags, status, req["received"], self.cfg.quote_valid_days,
                                      bool(ext.get("budgetary")), revision_of)
        rev_txt = f" (revises {revision_of['id']})" if revision_of else ""
        if revision_of:
            for rv in self.reviews:
                if rv["status"] == "Open" and rv["payload"].get("quote_id") == revision_of["id"]:
                    rv["status"] = f"Closed (superseded by {quote['id']})"
        self._stage(res, 5, "review" if flags else "done",
                    f"{quote['id']}{rev_txt}: ${total:,.2f}, {'trade' if is_trade else 'non-trade'} pricing; {status}")

        # ---- Stage 6: reserve
        if ext.get("budgetary"):
            self._stage(res, 6, "skipped", "Budgetary quote: no hold placed (customer said pricing only)")
        elif alloc_plan:
            so = self.erp.create_reservation(cust, quote["id"], alloc_plan, req["received"])
            quote["reservation_id"] = so["id"]
            cfa = ""
            if ext.get("cfa_requested"):
                cut = self.erp.create_cfa_order(cust, quote["id"], alloc_plan, req["email"], req["received"])
                quote["cfa_order_id"] = cut["id"]
                cfa = f"; CFA cuttings {cut['id']} from the held lots"
                cust_notes.append("A CFA (cutting for approval) from the lot we're holding is on its way.")
            self._stage(res, 6, "done", f"{so['id']} holds " + "; ".join(
                f"{l['sku']} " + "+".join(f"{a['yards']:g}yd@{a['lot']}" for a in l["allocation"]) for l in alloc_plan)
                + f" until {so['hold_expires']:%Y-%m-%d}{cfa}")
        else:
            self._stage(res, 6, "skipped", "Nothing in stock to reserve")

        self.crm.update_opportunity(opp, stage="Quote Sent" if status == "Sent" else "Quote Review", amount=total)
        res["email"] = emails.quote_email(req["name"], quote, line_desc, cust_notes, quote["valid_until"],
                                          bool(ext.get("budgetary")), trade=is_trade)
        res["quote_id"] = quote["id"]
        res["flags"] = flags
        if flags:
            self._review(res, "Price quote", f"{quote['id']}: " + " | ".join(flags),
                         "Approve and send the drafted quote email", "send_quote", {"quote_id": quote["id"]},
                         message=res["email"])
            res["outcome"] = f"Quote {quote['id']} drafted, needs review"
        else:
            self.log.record("CRM", "Email quote", f"{quote['id']} to {req['email']}",
                            "Salesforce: send email from Quote (template) / log EmailMessage")
            res["outcome"] = f"Quote {quote['id']} sent"

    # ------------------------------------------------------------------ human in the loop
    def approve(self, review_id: str, by: str = "rep"):
        rv = next(r for r in self.reviews if r["id"] == review_id)
        if rv["status"] != "Open":
            return rv
        res = self.results[rv["request"]]
        self.log.current_request, self.log.clock = rv["request"], res["request"]["received"]
        rv["status"] = f"Approved by {by}"
        self.log.record("Human", "Approve", f"{review_id}: {rv['proposed']}", "Salesforce Task closed / approval process")
        if rv["action"] in ("qualify_and_sample", "place_samples_capped"):
            lead = next(l for l in self.crm.leads if l["id"] == rv["payload"]["lead_id"])
            if rv["action"] == "qualify_and_sample":
                self.crm.set_lead_status(lead, "Qualified", f"approved by {by} ({review_id})")
                self._stage(res, 2, "done", f"Qualified by {by}")
            ident = identity.resolve(self.crm, res["request"])
            if ident["lead"] is lead and ident["contact"] is None:
                ident = {**ident, "lead": None}
            self._place_samples(res, lead, ident, approved_cap=True)
        elif rv["action"] == "send_quote":
            quote = next(q for q in self.crm.quotes if q["id"] == rv["payload"]["quote_id"])
            if quote["status"] == "Superseded":
                rv["status"] = "Closed (quote superseded)"
                return rv
            self.crm.set_quote_status(quote, "Sent")
            opp = next(o for o in self.crm.opportunities if o["id"] == quote["opp_id"])
            self.crm.update_opportunity(opp, stage="Quote Sent")
            self.log.record("CRM", "Email quote", f"{quote['id']} to {res['request']['email']}",
                            "Salesforce: send email from Quote (template)")
            self._stage(res, 5, "done", res["stages"][5]["summary"].replace("Pending rep review", f"Sent after review by {by}"))
            res["outcome"] = f"Quote {quote['id']} sent after review"
        elif rv["action"] == "send_question":
            self._email_question(rv, res, by)
        return rv

    def ask(self, review_id: str, by: str = "rep"):
        """Send the review's drafted question to the customer. For a qualification or sample-limit review the
        review stays open (the reply decides it); for a question-only review this is the whole action."""
        rv = next(r for r in self.reviews if r["id"] == review_id)
        if rv["status"] != "Open" or not rv.get("message") or rv["asked"] or rv["action"] == "send_quote":
            return rv  # a quote review's message is the quote itself: approving sends it
        res = self.results[rv["request"]]
        self.log.current_request, self.log.clock = rv["request"], res["request"]["received"]
        self._email_question(rv, res, by)
        return rv

    def _email_question(self, rv, res, by):
        self.log.record("CRM", "Email question", f"'{rv['message']['subject']}' to {res['request']['email']} ({rv['id']})",
                        "Salesforce: emailSimple action from quotes@, logged on the Contact")
        rv["asked"] = True
        if rv["action"] in ("send_question", "none"):
            rv["status"] = f"Question sent by {by}: waiting on customer"
            res["outcome"] = "Question sent: waiting on customer"
        else:
            res["outcome"] += " (question sent to customer)"

    def reject(self, review_id: str, by: str = "rep"):
        rv = next(r for r in self.reviews if r["id"] == review_id)
        if rv["status"] != "Open":
            return rv
        res = self.results[rv["request"]]
        self.log.current_request, self.log.clock = rv["request"], res["request"]["received"]
        rv["status"] = f"Rejected by {by}"
        self.log.record("Human", "Reject", f"{review_id}", "Salesforce Task closed")
        if rv["action"] == "send_quote":
            quote = next(q for q in self.crm.quotes if q["id"] == rv["payload"]["quote_id"])
            if quote.get("reservation_id"):
                self.erp.release_reservation(quote["reservation_id"], "quote rejected by rep")
            self.crm.set_quote_status(quote, "Rejected")
            res["outcome"] = "Quote rejected by rep (rework manually)"
        elif rv["action"] == "qualify_and_sample":
            lead = next(l for l in self.crm.leads if l["id"] == rv["payload"]["lead_id"])
            self.crm.set_lead_status(lead, "Disqualified", f"rejected by {by}")
            res["outcome"] = "Disqualified by rep"
        return rv
