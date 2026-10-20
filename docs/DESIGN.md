# Design note: Sample-to-Quote

## 1. The problem

The sample-to-quote journey crosses a website, a CRM and an ERP that don't talk to each other, so people carry the data: "messaging back and forth with customers and typing information from one form into another." That costs two things: **retyping** between systems, and **back-and-forth** with the customer while someone checks another system.

| Today | With the workflow |
|---|---|
| A CSR retypes the web form into a Salesforce Lead | The cart webhook creates the Lead, with the exact SKUs attached |
| A rep checks for duplicates, trade status, Do Not Sell | Duplicates and known accounts are matched automatically; a rep qualifies each new sender in one click |
| The rep emails Order Ops, who retypes the sample order into NetSuite | The NetSuite sample order is created and linked to the opportunity |
| The rep replies "checking stock and price", then works it out in a spreadsheet and retypes the quote | AI reads the email; NetSuite price and dye-lot stock fill the Salesforce Quote in one step |
| The rep emails to clarify color, quantity or trade status | Settled from the catalog and the customer's own samples; otherwise one drafted email |
| The rep emails Ops to hold yardage; old holds get forgotten | A one-lot hold is placed automatically and released on revision or after 14 days |

**The target:** no value is typed twice, and no customer waits on an internal email. On the seeded data, Dana Ruiz's journey goes from about 36 manual steps, 86 retyped fields and 8 internal emails to 3 rep clicks (qualifying her once, approving two flagged quotes). The manual-side numbers are illustrative estimates (`demo/baseline.py`).

## 2. Architecture

```
 Website (WooCommerce cart) ──webhook─────┐
 Shared inbox (quotes@perennialsfabrics.com)    ──Gmail push───┤
                                          ▼
                   Orchestrator: extract → identify → decide → act → escalate
                          │                                    │
                     CRM adapter (Salesforce)            ERP adapter (NetSuite)
```

**AI at the edges, deterministic in the middle.** The website needs no AI: on perennialsfabrics.com the customer adds an exact colorway from a product page, so the cart carries the SKU. Claude reads only the free-text channel, email, turning "80 yds of the navy stripe" into SKU + quantity. It uses structured outputs, its result is checked against the catalog, and a rules extractor runs as a cross-check (they agree on every SKU, quantity and unit across 13 test emails). Everything with money or inventory consequences (qualification, price, dye-lot allocation, holds) is plain, tested code, and customer emails are templates filled from ERP numbers, so no generated number reaches a customer.

The orchestrator talks to systems only through adapters (`MockCRM`, `MockERP`). Production swaps in `SalesforceCRM` / `NetSuiteERP` with the same methods, and the audit log already records the real API call behind each mock call. It would run as a small Python service on AWS: idempotent webhooks, a queue that keeps each customer's requests in order, retries with a dead-letter queue, and external ids on every cross-system record.

**Test data (a design decision).** Beyond the 21 provided requests, we added 6 edge-case rows to the workbook (marked in its Notes column; original kept in `case-study-prompt/`): a website quote in feet with CFA, quantities written as words, a real color tie during an open quote, a missing quantity, a discontinued fabric, and a quote from a sender whose trade check is still open. Two of them exposed real gaps that are now fixed: an ambiguous line could supersede an open quote, and the AI's reading of a sender could bypass a pending review. That second finding is one reason qualification is now manual for every new sender (§5).

## 3. Source of truth

| Data | Owner | Notes |
|---|---|---|
| People and companies, trade status, Do Not Sell, qualification outcome | **CRM** | ERP customer created on first order, keyed by the CRM Account Id |
| Opportunity, quote document and status, review tasks | **CRM** | The quote is what the customer saw |
| Items, status, list price, pricing rules | **ERP** | The CRM never stores its own prices |
| Inventory by dye lot, holds, sample / CFA / sales orders | **ERP** | The CRM shows a read-only reference (order number, hold expiry) |
| Raw inbound message | Website / inbox | Kept verbatim on the Lead for traceability |

## 4. How it maps to Salesforce and NetSuite

- **Intake:** WooCommerce `order.created` webhook (variant SKU = NetSuite item; Project Type, Length, CFA as line-item fields); Gmail API watch on quotes@perennialsfabrics.com for email.
- **Salesforce:** Lead (upserted on an external request id), lead convert through a small Apex endpoint, Opportunity, Quote + QuoteLineItem (items synced from NetSuite as Products), Tasks in a review queue, an Approval Process above $20k, and a Flow that calls the service when a rep approves.
- **NetSuite:** a pricing RESTlet (trade + volume + cut fee), sample and CFA order forms, lot-level holds, and a daily script that releases expired holds.
- **Caveat to settle with their admin:** a *Pending Approval* sales order doesn't commit inventory by default, so a real hold needs either an approved "Hold" order or a transfer to a hold location. The PoC keeps that choice inside the adapter.

The full list, with fields, scripts, owners and rollout, is in `production-handoff/README.md`, next to skeleton building blocks for each system.

## 5. Where a human stays in the loop

Automation handles the clear cases: spam, known trade accounts, clean quotes. People handle judgment and money:

- **Qualifying new senders.** Anyone without a CRM account waits for a rep's **Qualify** or **Reject**, with no system suggestion: trade status decides free samples and trade pricing, so a person makes that call. Known trade accounts, Do Not Sell and spam are still handled automatically.
- **Oversized or open-ended sample requests** (over 10, "everything"): narrow the list. This is also a sales conversation.
- **Inventory problems:** split dye lots (the customer approves a CFA from each lot), shortages, backorder vs. "ASAP".
- **High-value quotes** (over $20k): manager approval. **Do Not Sell** hits notify the account owner.
- **A color the system can't settle**, or Claude and the rules disagree.

Every other review carries a drafted customer message ("which 10 first?", one clarifying question, or the quote), so the rep's next step is one click, not an email thread. Reviews appear as Salesforce Tasks, where reps already work. Only flag-free quotes and routine sample confirmations are sent automatically.

## 6. With another week

1. **Real adapters in sandboxes** (Salesforce and NetSuite), settling the hold mechanism.
2. **A larger extraction eval:** about 100 labeled historical emails, to tune review thresholds from data.
3. **Project-level opportunity matching:** a designer runs several jobs at once; match on project, not "one open opportunity per account".
4. **The customer's decision (out of scope for this PoC):** an accept / decline link on the quote. Accept turns the hold into a sales order and marks the opportunity Closed Won; decline or expiry releases the hold and marks it Closed Lost, with a reminder before a hold ends. Today the loop ends when the quote is sent.
5. **Measure the funnel:** sample → quote → order conversion by segment. That is the business case.
