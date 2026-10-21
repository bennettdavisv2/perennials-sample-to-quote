# Design note: Sample-to-Quote

**The problem.** The website, Salesforce and NetSuite don't talk to each other, so people carry the data between them: retyping forms into other systems, and emailing customers back and forth while someone checks stock or price. **The goal:** no value typed twice, and no customer waiting on an internal email. In the demo, one customer's samples-to-quote journey drops from an estimated 36 manual steps and 86 retyped values to 3 rep clicks.

## 1. Architecture

![New flow: each step in the system where it runs](diagrams/new-flow.svg)

One integration service sits between the systems. Website orders arrive by webhook and quote emails by inbox push. Each request runs through the same pipeline: **read → identify the customer → decide → act in Salesforce and NetSuite → escalate anything uncertain to a rep.**

- **AI at the edges, deterministic in the middle.** Website carts already carry exact SKUs, so they need no AI. Claude reads only free-text email ("80 yds of the navy stripe" → SKU + quantity), with structured outputs, a catalog check and a rules cross-check. Qualification, pricing, dye-lot allocation and holds are plain, tested code, and customer emails are templates filled from ERP numbers.
- **Adapters.** The pipeline talks to systems only through a CRM and an ERP adapter. The PoC uses in-memory mocks; production swaps in Salesforce and NetSuite adapters with the same methods. The tests become the acceptance tests.
- **Test data.** We added 6 edge cases to the 21 provided requests (marked in the workbook's Notes column). They exposed two real bugs, both fixed.

## 2. Source of truth

| Data | Owner |
|---|---|
| People and companies, trade status, Do Not Sell, qualification | **Salesforce** |
| Opportunities, quotes sent to customers, review tasks | **Salesforce** |
| Items, list price, pricing rules | **NetSuite**: Salesforce never stores its own prices |
| Inventory by dye lot, holds, sample / CFA / sales orders | **NetSuite**: Salesforce shows a read-only reference |
| The raw order or email | Website / inbox, kept verbatim on the Lead |

NetSuite customers are created on the first order and keyed by the Salesforce Account Id, so the two systems stay linked.

## 3. Mapping onto Salesforce and NetSuite

- **Intake:** WooCommerce `order.created` webhook (each colorway is a variant SKU = a NetSuite item); Gmail API watch on quotes@perennialsfabrics.com.
- **Service:** a small Python service on AWS. Duplicate deliveries are processed once, each customer's requests run in order, and failures are retried, then parked in a dead-letter queue with an alarm.
- **Salesforce:** Lead → convert → Opportunity → Quote. Reviews are Tasks with Qualify / Approve / Reject buttons that call the service. An approval process covers quotes over $20k.
- **NetSuite:** a pricing script (trade, volume, cut fee), sample and CFA order forms, dye-lot holds, and a daily job that releases expired holds.
- **To settle first:** a *Pending Approval* sales order doesn't reserve stock by default, so the hold mechanism is a decision for Perennials' NetSuite admin.

Engineering's step-by-step plan is in [`production-handoff/ROADMAP.md`](../production-handoff/ROADMAP.md): about 9 weeks, starting with a read-only shadow mode.

## 4. Where a human stays in the loop

Automation handles the clear cases: spam, known trade accounts, clean quotes. People make the judgment and money calls:

- **Qualifying new senders.** Trade status decides free samples and trade pricing, so a rep clicks Qualify or Reject. The system makes no suggestion.
- **Quotes over $20k** go to a manager.
- **Inventory problems:** split dye lots, shortages, backorders.
- **Ambiguity:** a color the system can't settle, more than 10 samples, or Claude and the rules disagreeing.
- **Do Not Sell:** the request is blocked and the account owner is notified.

Each review comes with a drafted customer message, so the rep's next step is one click, not an email thread.

## 5. With another week

1. **Real adapters** against Salesforce and NetSuite sandboxes, settling the hold mechanism.
2. **An extraction eval** on about 100 labeled historical emails, to set review thresholds from data.
3. **The customer's decision:** an accept / decline link on the quote. Accepting turns the hold into an order; declining releases it.
4. **Project-level matching:** designers run several jobs at once, so match on project rather than one open opportunity per account.
5. **Funnel metrics:** sample → quote → order conversion by segment. That's the business case.
