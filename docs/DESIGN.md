# Design note: Sample-to-Quote

## 1. Architecture

```
 Website (WooCommerce cart) ──webhook──┐
 Shared inbox (quotes@)  ──poll/push───┤
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
                    (Salesforce / HubSpot)               (NetSuite)
```

The design principle is **AI at the edges, deterministic in the middle.** The website needs no AI for the fabric: on perennialsfabrics.com the customer adds an exact colorway from a product page, so the cart already carries the SKU. The model does the part that is still manual and fuzzy, the email channel: reading "80 yds of the navy stripe and maybe 20 of the boucle" and mapping it to SKUs. Everything with money or inventory consequences (qualification, price, dye-lot allocation, holds) is plain code that can be tested and audited. The LLM output is validated against the catalog (unknown SKUs are dropped and the line is flagged), and the rules extractor runs alongside as a cross-check. Customer emails are templates filled from ERP pricing, so no generated number reaches a customer.

The orchestrator talks to systems only through adapters (`MockCRM`, `MockERP`). Moving to production means writing `SalesforceCRM` / `NetSuiteERP` with the same methods. The audit log already records which real API call each mock call stands for.

## 2. Source of truth

| Data | Owner | Notes |
|---|---|---|
| People & companies (Lead, Contact, Account), trade status, Do Not Sell | **CRM** | ERP customer is created on first order, keyed by CRM Account Id (externalId) |
| Qualification decision + reason | **CRM** (Lead status) | Policy lives in code / Flow; outcome lives on the record |
| Opportunity, quote document, quote status | **CRM** | Quote is what the customer saw; it's attached to the Opportunity |
| Items, item status, list price, price rules | **ERP** | CRM never stores its own prices; it asks the ERP |
| Inventory by dye lot, reservations, sample + sales orders | **ERP** | CRM shows a read-only reference (SO number, hold expiry) |
| Raw inbound message | Website / inbox | Kept verbatim on the Lead / Opportunity for traceability |

## 3. Mapping to real systems

| PoC step | Salesforce | NetSuite |
|---|---|---|
| Website sample / quote cart | WooCommerce order webhook (line items = variant SKUs; Project Type, Length, Date Needed, CFA as line-item meta; order note) → orchestrator → `POST /sobjects/Lead` (LeadSource = Web Sample) | Variant SKU = NetSuite item (externalId) |
| Dedupe | SOQL on Contact/Lead email + email domain; Duplicate Rules as a backstop | – |
| Qualification | Lead Status + `Qualification_Reason__c`; review = Task to a queue | – |
| Convert + Opportunity | Lead convert API (to existing or new Account/Contact), Opportunity + Contact Role | Customer record (`externalId` = Account Id) |
| Sample order | `Sample_Order__c` lookup on Opportunity | Sales Order, Sample form, $0 price level |
| Quote email intake | Email-to-Case or Gmail/Graph API → orchestrator | – |
| Pricing | Quote + QuoteLineItem; Quote PDF via ContentVersion | Price levels + quantity pricing, or a RESTlet that applies trade/volume/cut-fee rules |
| Reservation | Hold SO number + expiry on Quote | Lot-numbered items; sales order with lot-level inventory detail (see caveat) |
| CFA (cutting for approval) | CFA order number on Quote | $0 sales order, CFA form, lot-specific cutting from the held lot |
| Revision | New Quote version; old one Superseded | Close old hold lines, create new |
| Human review | Task / Approval Process on Quote (discount, value thresholds) | – |

**NetSuite caveat to confirm with their admin:** a Sales Order in *Pending Approval* does not commit inventory by default. Real holds need either (a) an approved SO with a custom "Hold" status plus a scheduled script that closes it at expiry, or (b) a transfer to a "Held" bin/location. The PoC models the hold explicitly so this choice stays inside the adapter.

**Where it runs:** a small service (Python on AWS Lambda/Cloud Run, or inside an iPaaS like Celigo or Workato if Perennials already uses one for the Salesforce-NetSuite sync). Requirements: idempotency keys (inbound message ID), retries with dead-letter queue, external IDs on every cross-system record, and the audit log persisted.

## 4. Where a human stays in the loop

Automation handles the clear cases: spam, known trade accounts, clean quotes. People handle judgment and money:

- **Qualification gray zone:** trade language on a personal email address, or no signal. A rep verifies the resale certificate or website.
- **Open-ended or oversized sample asks** ("everything you have", over 10 SKUs). A rep narrows the list. This is also a sales conversation worth having.
- **Anything the AI inferred from an email** ("green velvet" read as Moss), or where Claude and the rules disagree. Website carts don't need this: the SKU is exact.
- **Inventory problems:** split dye lots (the customer approves a CFA from each lot), shortages, backorder vs. "ASAP". These need purchasing/production input on lead time.
- **High-value quotes** (over $20k in the PoC) go to a manager. Policy changes, such as discount overrides, belong to sales ops.
- **Do Not Sell** hits notify the account owner.

Every customer email is drafted. Sending is automatic only for flag-free quotes and routine sample confirmations. Review items are mirrored as CRM Tasks so reps work where they already are.

## 5. With another week

1. **Real adapters in a sandbox:** a Salesforce developer org and NetSuite sandbox. Settle the reservation mechanism, and run lead convert against real duplicate rules.
2. **Evaluation set for extraction:** about 100 labeled historical requests. Measure Claude vs. rules on SKU and quantity accuracy, and tune the review thresholds from data rather than guesses.
3. **Project-level opportunity matching:** a designer can have several jobs at once. Match on project text/location rather than "one open opp per account".
4. **Customer-facing loop:** quote acceptance link → converts the held order to a real SO. Hold-expiry reminders ("your hold ends Friday, extend?").
5. **Persistence and ops:** Postgres for state and audit, idempotent webhook handling, alerting on review-queue age.
6. **Measure the funnel:** sample → quote → order conversion by segment. This is the business case for the project.
