# Design note: Sample-to-Quote

## 1. The problem

Today the sample-to-quote journey crosses three systems (website, CRM, ERP) that don't talk to each other well. As the brief puts it, the handoff is manual: "people are messaging back and forth with customers and typing information from one form into another." That costs two things: **retyping** between systems, and **back-and-forth** with the customer while someone checks another system. Each handoff below is a place where that happens today, and the row says what replaces it.

| # | Today | Cost | With the workflow |
|---|---|---|---|
| 1 | A web sample form arrives as an email; a CSR retypes it into a Salesforce Lead | Retyping | The cart webhook creates the Lead, with the exact SKUs already attached |
| 2 | A rep checks whether this is a known customer, a duplicate, or Do Not Sell | Manual lookup; duplicate records | Identity match and a qualification policy table, in seconds; reps see only the gray zone |
| 3 | The rep emails Order Ops; Ops retypes the sample order into NetSuite | Retyping + an internal email | The sample order is created in NetSuite and linked to the Salesforce opportunity |
| 4 | The customer emails for a quote; the rep replies "checking stock and price" | Back-and-forth | AI reads the email; price and dye-lot stock come back in the same step |
| 5 | The rep works out the price in a spreadsheet and retypes the quote into Salesforce | Retyping; pricing errors | NetSuite pricing rules fill the Salesforce Quote; no number is typed by hand |
| 6 | The rep emails the customer to clarify color, quantity or trade status | Back-and-forth | Settled from the catalog and the customer's own samples; otherwise one drafted email with every question |
| 7 | The rep emails Ops to hold yardage; Ops picks a lot and keys an order; old holds get forgotten | Retyping; stale holds | A hold from one dye lot is placed automatically, and released on revision or after 14 days |

**The target:** no value is typed twice, and a customer never waits on an internal email. People stay in the loop only for judgment (§5). On the seeded data, Dana Ruiz's journey (two sample requests, a quote and a revision) is about 35 manual steps, 84 retyped fields and 8 internal emails today, versus 2 rep approvals with the workflow. The manual-side numbers are illustrative estimates (`s2q/baseline.py`), not measurements.

## 2. Architecture

The README shows the same flow as diagrams; `ENGINEERING_HANDOFF.md` is the build list for each system.

```
 Website (WooCommerce cart) ──webhook──┐
 Shared inbox (quotes@)  ──Gmail push───┤
                                       ▼
                       ┌──────── Orchestrator (integration service) ────────┐
                       │ 1 Extract     web: cart is structured (exact SKUs) │
                       │               email: AI free text -> JSON, validated│
                       │ 2 Identify    dedupe against CRM                    │
                       │ 3 Decide      qualification + quote policy (rules)  │
                       │ 4 Act         CRM / ERP adapter calls               │
                       │ 5 Escalate    review item + CRM Task when unsure    │
                       └────────┬──────────────────────────────┬────────────┘
                                ▼                              ▼
                         CRM adapter                    ERP adapter
                      (Salesforce)                       (NetSuite)
```

The design principle is **AI at the edges, deterministic in the middle.** The website needs no AI for the fabric: on perennialsfabrics.com the customer adds an exact colorway from a product page, so the cart already carries the SKU. The model does the part that is still manual and fuzzy, the email channel: reading "80 yds of the navy stripe and maybe 20 of the boucle" and mapping it to SKUs. Everything with money or inventory consequences (qualification, price, dye-lot allocation, holds) is plain code that can be tested and audited. The LLM output is validated against the catalog (unknown SKUs are dropped and the line is flagged), and the rules extractor runs alongside as a cross-check. Customer emails are templates filled from ERP pricing, so no generated number reaches a customer.

The orchestrator talks to systems only through adapters (`MockCRM`, `MockERP`). Moving to production means writing `SalesforceCRM` / `NetSuiteERP` with the same methods. The audit log already records which real API call each mock call stands for.

## 3. Source of truth

| Data | Owner | Notes |
|---|---|---|
| People & companies (Lead, Contact, Account), trade status, Do Not Sell | **CRM** | ERP customer is created on first order, keyed by CRM Account Id (externalId) |
| Qualification decision + reason | **CRM** (Lead status) | Policy lives in code / Flow; outcome lives on the record |
| Opportunity, quote document, quote status | **CRM** | Quote is what the customer saw; it's attached to the Opportunity |
| Items, item status, list price, price rules | **ERP** | CRM never stores its own prices; it asks the ERP |
| Inventory by dye lot, reservations, sample + sales orders | **ERP** | CRM shows a read-only reference (SO number, hold expiry) |
| Raw inbound message | Website / inbox | Kept verbatim on the Lead / Opportunity for traceability |

## 4. Mapping to real systems

| PoC step | Salesforce | NetSuite |
|---|---|---|
| Website sample / quote cart | WooCommerce order webhook (line items = variant SKUs; Project Type, Length, Date Needed, CFA as line-item meta; order note) → orchestrator → `POST /sobjects/Lead` (LeadSource = Web Sample) | Variant SKU = NetSuite item (externalId) |
| Dedupe | SOQL on Contact/Lead email + email domain; Duplicate Rules as a backstop | – |
| Qualification | Lead Status + `Qualification_Reason__c`; review = Task to a queue | – |
| Convert + Opportunity | Lead convert through a small Apex REST endpoint wrapping `Database.convertLead` (to existing or new Account/Contact), Opportunity + Contact Role | Customer record (`externalId` = Account Id) |
| Sample order | `Sample_Order__c` lookup on Opportunity | Sales Order, Sample form, $0 price level |
| Quote email intake | Gmail API watch on quotes@ → Pub/Sub push → orchestrator; replies sent from Salesforce so they're logged | – |
| Pricing | Quote + QuoteLineItem (needs each item as a Product with a price-book entry, synced from NetSuite); Quote PDF | RESTlet that applies the trade / volume / cut-fee rules |
| Reservation | Hold SO number + expiry on Quote | Lot-numbered items; sales order with lot-level inventory detail (see caveat) |
| CFA (cutting for approval) | CFA order number on Quote | $0 sales order, CFA form, lot-specific cutting from the held lot |
| Revision | New Quote version; old one Superseded | Close old hold lines, create new |
| Human review | Task / Approval Process on Quote (discount, value thresholds) | – |

**NetSuite caveat to confirm with their admin:** a Sales Order in *Pending Approval* does not commit inventory by default. Real holds need either (a) an approved SO with a custom "Hold" status plus a scheduled script that closes it at expiry, or (b) a transfer to a "Held" bin/location. The PoC models the hold explicitly so this choice stays inside the adapter.

**Where it runs:** a small Python service on AWS (API Gateway, Lambda, SQS FIFO grouped by customer so one customer's requests run in order, Postgres for state and the audit log). Requirements: idempotency keys (order id / message id), retries with a dead-letter queue, and external ids on every cross-system record. If Perennials already runs an iPaaS (Celigo, Workato) for the Salesforce–NetSuite sync, the same adapters can sit behind it.

## 5. Where a human stays in the loop

Automation handles the clear cases: spam, known trade accounts, clean quotes. People handle judgment and money:

- **Qualification gray zone:** trade language on a personal email address, or no signal. A rep verifies the resale certificate or website.
- **Open-ended or oversized sample asks** ("everything you have", over 10 SKUs). A rep narrows the list. This is also a sales conversation worth having.
- **A color the system can't settle on its own.** A unique match ("green velvet" = Moss) is quoted and named in the email; several matches are resolved from the customer's sample history (what we sampled to them is what they're quoting). Only a real tie becomes a drafted one-line question with stock per colorway. Also: Claude and the rules disagree, or Claude named a SKU that doesn't exist. Website carts need none of this: the SKU is exact.
- **Inventory problems:** split dye lots (the customer approves a CFA from each lot), shortages, backorder vs. "ASAP". These need purchasing/production input on lead time.
- **High-value quotes** (over $20k in the PoC) go to a manager. Policy changes, such as discount overrides, belong to sales ops.
- **Do Not Sell** hits notify the account owner.

Every review item carries a drafted customer message (trade verification, a "pick your 10" list, one clarifying question, or the quote), so when a person is needed the next step is one click, not an email thread. Every customer email is drafted. Sending is automatic only for flag-free quotes and routine sample confirmations. Review items are mirrored as CRM Tasks so reps work where they already are.

## 6. With another week

1. **Real adapters in a sandbox:** a Salesforce developer org and NetSuite sandbox. Settle the reservation mechanism, and run lead convert against real duplicate rules.
2. **Evaluation set for extraction:** about 100 labeled historical requests. Measure Claude vs. rules on SKU and quantity accuracy, and tune the review thresholds from data rather than guesses.
3. **Project-level opportunity matching:** a designer can have several jobs at once. Match on project text/location rather than "one open opp per account".
4. **Customer-facing loop:** quote acceptance link → converts the held order to a real SO. Hold-expiry reminders ("your hold ends Friday, extend?").
5. **Persistence and ops:** Postgres for state and audit, idempotent webhook handling, alerting on review-queue age.
6. **Measure the funnel:** sample → quote → order conversion by segment. This is the business case for the project.
