# Perennials: Sample-to-Quote PoC

Today the sample-to-quote journey crosses three systems that don't talk to each other: the website, the CRM (Salesforce) and the ERP (NetSuite). People retype the same information from one into the next and email customers back and forth. This PoC puts one integration layer between them. Every request goes through all six stages (lead, qualification, sample order + opportunity, quote request, price quote, inventory reservation) with no retyping, and a person steps in only when a judgment call is needed.

## Results

| One customer: samples, a quote and one change | By hand today | With the integration |
|---|---|---|
| Staff time | 15 min 22 s | 1 click (qualify a new customer) |
| Values typed by hand | 56 | 0 |
| Emails written by staff | 6 | 0 |
| Switches between systems | 12 | 0 |
| Request to quote sent | Hours to days, waiting on email (estimate) | Under 1 s from the website, about 8 s from an email |

The manual column was measured on the demo's Today (manual) page; the integration column is the same journey in the new system. Email reading, scored against hand-labeled answers for all 13 workbook emails (`python -m s2q.eval`): Claude 13/13, the rules parser 12/13, with any disagreement routed to a rep. 53 automated tests cover the workflow.

## Run it

Requires Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

streamlit run demo/app.py     # demo at http://localhost:8501/
```

**Optional: use Claude for email extraction.** Run `export ANTHROPIC_API_KEY=sk-...` before starting. If the key is in a `.env` one folder up, load it with `set -a; source ../.env; set +a`. Without a key, the deterministic rules extractor is used and everything works the same. With a key, Claude reads each email and the rules run as a cross-check; if they disagree, the request goes to review.

## Architecture

![New flow: each step in the system where it runs](docs/diagrams/new-flow.svg)

## Repo Contents

| Folder | Contents |
|---|---|
| [`s2q/`](s2q/) | The shared core: workflow, intake (website cart + email), dedupe, qualification, pricing, email templates, and the CRM / ERP adapter interface with in-memory mocks. Tested; production runs it unchanged. |
| [`demo/`](demo/) | The walkthrough app (storefront, CRM, ERP, today's manual process, Old vs New, ops console), its data (the workbook plus 6 added edge cases) and a filming guide. |
| [`production-handoff/`](production-handoff/) | Implementation guidance for engineering: a phased [roadmap](production-handoff/ROADMAP.md) of what to build first. |
| [`production-handoff/woocommerce/`](production-handoff/woocommerce/) | Plugin that saves the product-page fields onto the order, and the order webhook setup. |
| [`production-handoff/integration-service/`](production-handoff/integration-service/) | The AWS service: webhook, Gmail-push and Salesforce-callback handlers, the queue worker, Salesforce / NetSuite adapters, database schema and deployment template. |
| [`production-handoff/salesforce/`](production-handoff/salesforce/) | Apex lead-convert endpoint, field metadata, and specs for the review queue, approval process and callback Flow. |
| [`production-handoff/netsuite/`](production-handoff/netsuite/) | Daily hold-expiry script, and the pricing-rule record. |
| [`production-handoff/gmail/`](production-handoff/gmail/) | The watch on quotes@perennialsfabrics.com that pushes new mail to the service. |