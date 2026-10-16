# Perennials: Sample-to-Quote PoC

A small, runnable proof of concept for the Perennials sample-to-quote workflow. It takes each inbound request (website sample forms, quote emails) through all six stages: lead, qualification, sample order + opportunity, quote request, price quote, and inventory reservation. It runs against mock CRM and ERP adapters seeded from `data/perennials_sample_data.xlsx`.

Anything the rules aren't sure about goes to a **review queue** instead of being guessed. Every system call is logged with the real Salesforce / NetSuite API call it maps to.

## Run it (under 5 minutes)

Requires Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

streamlit run app.py          # UI at http://localhost:8501
python -m s2q.cli -v          # or headless: every request, stage by stage, with email drafts
pytest -q                     # 14 tests
```

**Optional: use Claude for extraction.** Run `export ANTHROPIC_API_KEY=sk-...` before starting. Set `S2Q_MODEL` to override the model (default `claude-sonnet-5-5`). Without a key, the app uses the deterministic rules extractor and works exactly the same. With a key, Claude does the extraction and the rules extractor runs as a cross-check. If they disagree, the request is flagged for review.

## What to click

1. Click **▶ Next request** to step through the 21 requests in time order, or **⏭ Process all**.
2. **Inbox & pipeline**: one row per request with a ✅🟡⛔ status per stage. Pick a request to see the message, identity match, qualification reasons, AI extraction, quote lines, flags, and the drafted customer email.
3. **Review queue**: approve or reject. Approving runs the deferred action: it places the samples, or sends the quote.
4. **CRM / ERP**: the mock systems' records. Watch "reserved" change on the dye lots.
5. **Audit log**: every call, with the real API it maps to.

## Interesting rows

| Request | What happens | Why |
|---|---|---|
| WEB-003 | Dana Ruiz from `d.ruiz@` is matched to the same contact, and the email is added as an alternate | Same domain + same name; prevents a duplicate lead/opportunity |
| WEB-005 | Disqualified, no samples or price list, account owner notified | CRM account is *Do Not Sell* (competitor) |
| WEB-007 | Spam is filtered and nothing is written to CRM | Keeps the CRM clean |
| WEB-008 | Qualified, but Sunset Ikat is excluded from samples; the email offers the 22 yd remaining | Discontinued: no new samples |
| WEB-002, WEB-009 | Non-trade nurture email, no free samples | Consumer / student |
| WEB-012 | Goes to review | Says "designer" but uses a personal Gmail address |
| WEB-013 | Goes to review | 14 SKUs requested, max 10 |
| EML-014 | Quote with 20% (trade + volume) on 80 yd stripe; held across **two dye lots** goes to review | No single lot covers 80 yd |
| EML-015 | 12 m becomes 13.25 yd; "green velvet" is read as Velvet Plush Moss and flagged to confirm; out of stock, so not reserved | Unit conversion + inferred color + zero stock |
| EML-016 | $34.9k quote, 120 yd short on Canvas White, goes to manager review | Shortage + split lot + high value + need-by date |
| EML-017 | Clean quote with the $25 cut fee is **sent automatically** and held | No flags |
| EML-018 | Budgetary quote, no hold placed | Customer said pricing only |
| EML-019 | Backordered (ETA 11/15) vs. "ASAP": priced, not held, goes to review | Can't reserve what isn't there |
| EML-020 | Student is quoted list price + cut fee; becomes a consumer account | Non-trade pricing |
| EML-021 | **Revises** Q-0101 to v2: the old hold is released and a new hold placed (87 of 90 yd available) | Follow-up on the same job |

## Layout

```
app.py                  Streamlit UI
s2q/workflow.py         Orchestrator: the six stages, review queue, approve/reject
s2q/extract.py          Free text -> structured request (Claude tool-use, or rules fallback)
s2q/identity.py         Match sender to existing lead/contact/account (dedupe)
s2q/qualify.py          Qualification policy table
s2q/pricing.py          Pricing math (pure functions)
s2q/emails.py           Customer email templates (numbers come only from pricing)
s2q/adapters/crm.py     Mock Salesforce
s2q/adapters/erp.py     Mock NetSuite (items, dye-lot inventory, sample orders, reservations)
s2q/data.py             Loads the workbook; pricing rules are parsed from the Pricing Rules tab
docs/DESIGN.md          Design note (architecture, sources of truth, mapping, human-in-the-loop, next week)
docs/AI_USAGE.md        How AI was used to build this, and inside it
```

## Assumptions

Ambiguities in the brief and data, and the call I made on each:

1. **Volume tiers are trade-only and additive.** "On top of trade discount" means 15% + 5% = 20% off list, not compounded (19.25%). Non-trade pays list price at any quantity.
2. **Cut fee** is $25 per line under 5 yd, for everyone.
3. **Meters are converted to yards and rounded up to the nearest 1/4 yd** (12 m becomes 13.25 yd).
4. **Samples are memo swatches stocked separately from bolt yardage.** Out-of-stock or backordered fabrics can still be sampled (the email notes the yardage status). Discontinued fabrics cannot.
5. **Free samples are for qualified trade only.** Consumers and students get a friendly nurture email with a paid-sample/retail path, not a rejection.
6. **A designer on a personal email address goes to human review**, not auto-qualify or auto-reject.
7. **Do Not Sell** accounts are disqualified: no samples, no price list, and the account owner is notified.
8. **Spam never reaches the CRM.**
9. For existing contacts, a lead is still created (for source attribution) and **converted into the existing contact**, as Salesforce lead convert does.
10. **Same email domain + same name means the same person.** The new address is added as an alternate email.
11. **One open opportunity per account is reused** for follow-ups. In production this would match on project (see design note).
12. **A follow-up that says "update" or touches the same SKUs revises the open quote** (v1 to v2). The old hold is released before re-checking availability.
13. **Inventory is held at quote time, even while the quote waits for review.** Holds expire in 14 days and are cheap to release. Budgetary quotes and out-of-stock/backordered lines are not held.
14. **Dye lots:** prefer the smallest single lot that covers the whole line. If a split is needed, the quote goes to review (the customer must approve mixed lots).
15. **Shortage:** quote the full quantity, hold what's available, flag the gap. **Discontinued:** quote at most the remaining stock.
16. **Any flag, or a total over $20k, sends a quote to review.** Clean quotes are sent automatically.
17. Simulated "now" is each request's received time (quote valid 30 days, hold 14 days). Shipping and tax are excluded.
18. The sheet's *Type* column is used for sample vs. quote routing. In production the LLM would classify intent for the shared inbox.
