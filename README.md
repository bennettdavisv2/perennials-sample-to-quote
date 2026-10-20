# Perennials: Sample-to-Quote PoC

Today the sample-to-quote journey crosses three systems that don't talk to each other: the website, the CRM (Salesforce) and the ERP (NetSuite). People retype the same information from one into the next and email customers back and forth. This PoC puts one integration layer between them. Every request goes through all six stages (lead, qualification, sample order + opportunity, quote request, price quote, inventory reservation) with no retyping, and a person steps in only when a judgment call is needed.

## How it works

![New flow: each step in the system where it runs](docs/diagrams/new-flow.svg)

**Dana Ruiz's journey (two sample requests, a quote and a revision): about 36 manual steps and 86 retyped fields today → 3 rep clicks with the workflow** (qualify her once, approve two flagged quotes). Manual-side numbers are labelled estimates.

## What's in this repo

| Folder | What's inside |
|---|---|
| [`s2q/`](s2q/) | The shared core: workflow, intake (website cart + email), dedupe, qualification, pricing, email templates, and the CRM / ERP adapter interface with in-memory mocks. Tested; production runs it unchanged. |
| [`demo/`](demo/) | The walkthrough app (storefront, CRM, ERP, Old vs New, ops console), its data (the workbook plus 6 added edge cases) and a filming guide. |
| [`production-handoff/`](production-handoff/) | The [system-by-system build list](production-handoff/README.md) for engineering, with owners, sizes, rollout and open questions. The building blocks are below; they're skeletons and specs, not yet run against real systems. |
| [`production-handoff/woocommerce/`](production-handoff/woocommerce/) | Plugin that saves the product-page fields onto the order, and the order webhook setup. |
| [`production-handoff/integration-service/`](production-handoff/integration-service/) | The AWS service: webhook, Gmail-push and Salesforce-callback handlers, the queue worker, Salesforce / NetSuite adapters, database schema and deployment template. |
| [`production-handoff/salesforce/`](production-handoff/salesforce/) | Apex lead-convert endpoint, field metadata, and specs for the review queue, approval process and callback Flow. |
| [`production-handoff/netsuite/`](production-handoff/netsuite/) | Pricing RESTlet, daily hold-expiry script, and the pricing-rule record. |
| [`production-handoff/gmail/`](production-handoff/gmail/) | The watch on quotes@perennialsfabrics.com that pushes new mail to the service. |
| [`docs/`](docs/) | Design note, AI usage notes, and the diagram source. |
| [`case-study-prompt/`](case-study-prompt/) | Bertram's original brief and workbook, unchanged. |

## Run it (under 5 minutes)

Requires Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

streamlit run demo/app.py     # demo at http://localhost:8501/
python -m s2q.cli -v          # or headless: every workbook request, stage by stage, with email drafts
pytest -q                     # 44 tests
```

**Optional: use Claude for email extraction.** Run `export ANTHROPIC_API_KEY=sk-...` before starting. If the key is in a `.env` one folder up, load it with `set -a; source ../.env; set +a`. Set `S2Q_MODEL` to override the model (default `claude-opus-5-5`, low effort). Without a key, the deterministic rules extractor is used and everything works the same. With a key, Claude reads each email and the rules run as a cross-check; if they disagree, the request goes to review. Website carts are structured, so they never go to the LLM.

## We extended the test data

The 21 requests Bertram provided all pass, but they don't exercise several cases the workflow has to handle, so we added **6 rows** to the workbook's Inbound Requests tab. Each is marked in a new Notes column and in the Read Me tab; the original file is unchanged in `case-study-prompt/`.

| Row | Edge case |
|---|---|
| WEB-014 | Website quote form: 90 feet becomes 30 yd, CFA requested, a date needed |
| EML-022 | Quantities written as words ("sixty yards"): the rules can't read them, Claude can, and the disagreement goes to review |
| EML-023 | A real color tie ("the linen", both colors sampled) while a linen quote is open: one drafted question, and the open quote is left alone |
| EML-024 | No quantity given: one drafted question |
| EML-025 | Discontinued fabric: only the 22 yd that remain are quoted |
| EML-026 | A quote from a sender still waiting to be qualified: it waits for the rep |

Two of these exposed real bugs, both fixed: an ambiguous color could replace an open quote and release its hold, and Claude's reading of a sender could skip an open review.

**What the 44 tests cover:** the pricing math (trade and volume discounts, cut fee, meters and feet); the outcome of all 27 rows end to end; dedupe, spam, revisions, holds and backorders; color resolution and the drafted customer messages; manual qualification (qualify, reject, qualify-then-quote, Do Not Sell); website carts and Claude's output validation and fallback; the demo's entry points and old-vs-new numbers; and that the production adapters match the mocks' interface.

## Assumptions

Ambiguities in the brief and data, and the call I made on each:

1. **Volume tiers are trade-only and additive.** "On top of trade discount" means 15% + 5% = 20% off list, not compounded (19.25%). Non-trade pricing (list price) stays in the pricing function, but the workflow only prices for qualified trade customers.
2. **Cut fee** is $25 per line under 5 yd, for everyone.
3. **Meters and feet are converted to yards and rounded up to the nearest 1/4 yd** (12 m becomes 13.25 yd; 10 ft becomes 3.5 yd). The site's quote form offers Yards / Feet / Meters.
4. **Samples are memo swatches stocked separately from bolt yardage.** Out-of-stock or backordered fabrics can still be sampled (the email notes the yardage status). Discontinued fabrics cannot.
5. **Free samples and trade pricing are for qualified trade only.** Anyone who isn't trade (a homeowner, a student, an existing non-trade account) goes to a rep, who can reject them; non-trade buyers are then handled outside this system.
6. **Qualification is manual for new senders.** Anyone without a CRM account waits for a rep's **Qualify** or **Reject**, with no suggestion from the system: what a sender says about themselves never qualifies them. Spam, existing trade accounts, existing consumer accounts and Do Not Sell are still handled automatically. The demo's seeded history includes the rep's decisions (`demo/data/seed_decisions.json`); Hannah Kim's are left open to show the step live.
7. **Do Not Sell** accounts are disqualified: no samples, no price list, and the account owner is notified.
8. **Spam never reaches the CRM.**
9. For existing contacts, a lead is still created (for source attribution) and **converted into the existing contact**, as Salesforce lead convert does.
10. **Same email domain + same name means the same person.** The new address is added as an alternate email.
11. **One open opportunity per account is reused** for follow-ups. In production this would match on project (see design note).
12. **A follow-up that says "update" or touches the same SKUs revises the open quote** (v1 to v2). The old hold is released before re-checking availability.
13. **Inventory is held at quote time, even while the quote waits for review.** Holds carry a 14-day expiry and are cheap to release (the PoC records the expiry; the release job is in the engineering handoff). The customer's accept / decline step is out of scope. Budgetary quotes and out-of-stock/backordered lines are not held.
14. **Dye lots:** prefer the smallest single lot that covers the whole line. If a split is needed, the quote goes to review (the customer must approve mixed lots).
15. **Shortage:** quote the full quantity, hold what's available, flag the gap. **Discontinued:** quote at most the remaining stock.
16. **Any flag, or a total over $20k, sends a quote to review.** Clean quotes are sent automatically.
17. Simulated "now" is each request's received time; live demo submissions are stamped an hour after the latest request (quote valid 30 days, hold 14 days). Shipping and tax are excluded.
18. **Website requests are structured, like the real site.** The brief describes a free-text form, but on perennialsfabrics.com a sample is added to the cart from a product page (one colorway = one variant SKU, plus a Project Type), and "Request A Quote" sends Length + unit, Date Needed, CFA Waived / Requested and Project Name. So a web customer cannot name a fabric that doesn't exist, and AI extraction is only used on email. Each WEB row was converted once into its cart (`demo/data/web_cart_submissions.json`); the original message is kept as the order note, and "everything" / "all your solids" / "every color of X" became the SKUs those imply. A cart SKU missing from the ERP (e.g. a stale cart) is flagged, never substituted.
19. **Guest sample checkout is allowed.** The real site steers samples through a trade account (resale number), which would move qualification to registration. Allowing guest checkout keeps lead qualification (stage 2) meaningful for this exercise.
20. **CFA (cutting for approval)** is the term for the customer approving a dye lot. A split across lots asks for a CFA from each lot; "CFA Requested" on the web quote form creates a CFA cutting order from the held lot.
21. **Every review comes with a drafted customer message,** so a rep's next step is one click instead of a thread: a "which 10 first?" pick list, one clarifying question (color tie or missing quantity), or the quote itself. Sending the pick list keeps the sample review open until the customer replies. Qualification reviews are the exception: the rep decides with Qualify / Reject.
22. **Colors are resolved before anyone is asked.** If an email's description fits exactly one catalog SKU ("green velvet" = Moss), it is quoted and named in the email, with no hold. If several colorways fit ("the canvas"), the customer's own sample orders decide it. Only if that still leaves more than one does the system draft a single question listing the colorways and current stock.
23. The sheet's *Type* column is used for sample vs. quote routing. In production the LLM would classify intent for the shared inbox.
