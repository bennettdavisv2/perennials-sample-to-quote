# Production handoff

Implementation guidance for engineering: how to take the sample-to-quote PoC into production at Perennials, what to build first, and what has to be decided along the way. The business logic is the tested core in [`s2q/`](../s2q/); production runs it with real Salesforce and NetSuite adapters instead of the in-memory mocks, and its tests become the acceptance tests.

## Read in this order

| File | What it's for |
|---|---|
| [ROADMAP.md](ROADMAP.md) | **Start here.** The priority list: seven phases in build order, each step with owner, size, dependencies and a "done when" check |
| [DECISIONS.md](DECISIONS.md) | Questions only Perennials can answer, each with a recommended default and the step it blocks |
| [RISKS.md](RISKS.md) | What's most likely to go wrong and which phase deals with it |
| [REFERENCE.md](REFERENCE.md) | The detailed specs by system: fields, scripts, endpoints, settings. The roadmap's item numbers (W1, S2, N8…) point here. §7 covers where the Salesforce and NetSuite MCP servers fit, and why the pipeline doesn't use them |

## The plan at a glance

| Phase | Goal | Weeks |
|---|---|---|
| 0. Decide and set up | Blocking decisions answered, sandboxes and access in place, core refactors | 1 |
| 1. Clean the data | SKUs match NetSuite, accounts linked to customers, fields deployed | 2 |
| 2. Shadow mode | Live traffic processed end to end, **nothing written**, results compared with what reps did | 3–5 |
| 3. Leads and samples | Leads, qualification tasks and sample orders written automatically | 5–6 |
| 4. Quotes, all reviewed | Quotes priced and created; every quote approved by a rep | 6–7 |
| 5. Holds | Dye-lot holds, CFA cuttings, daily hold expiry | 8 |
| 6. Auto-send | Clean quotes go out without a click | 9 |

About **9 weeks** for one integration engineer with part-time WooCommerce, Salesforce and NetSuite admins. The biggest risks are the NetSuite hold mechanism and the Salesforce product sync ([RISKS.md](RISKS.md)).

## Building blocks

Skeletons and specs: each file shows the shape, the exact API calls and what's left to write. None of it has been deployed or run against a real WooCommerce site, Salesforce org or NetSuite account. `tests/test_handoff.py` checks that the adapters cover every method the workflow uses, and tests the webhook signature check.

| Folder | What's inside | Roadmap steps |
|---|---|---|
| [woocommerce/](woocommerce/) | Plugin that saves the product-page fields onto the order; order webhook setup and payload contract | 1.1, 2.1 |
| [gmail/](gmail/) | The watch on quotes@perennialsfabrics.com that pushes new mail to the service | 2.2 |
| [integration-service/](integration-service/) | AWS service: webhook, Gmail-push and Salesforce-callback handlers, queue worker, Salesforce and NetSuite adapters, database schema, deployment template, and the `s2q/` refactors | 0.4, 2.3, 2.4, 3.x–6.1 |
| [salesforce/](salesforce/) | Apex lead-convert endpoint, field metadata, specs for the review queue, approval process, callback Flow and integration user | 1.4, 3.1, 3.2, 4.3–4.5 |
| [netsuite/](netsuite/) | Pricing RESTlet, daily hold-expiry script, pricing-rule record | 1.5, 1.6, 4.2, 5.1–5.3 |

## Assumed stack

| Layer | Choice |
|---|---|
| Website | WooCommerce on WordPress (each colorway is a product variation, as on perennialsfabrics.com) |
| CRM | Salesforce Sales Cloud, Enterprise edition or above, with Quotes enabled |
| ERP | NetSuite with Lot Numbered Inventory (one lot number = one dye lot) |
| Integration | Python service on AWS: API Gateway, Lambda, SQS FIFO, RDS Postgres, Secrets Manager, EventBridge |
| Inbound email | Google Workspace: quotes@perennialsfabrics.com watched through the Gmail API |
| AI | Claude through the Anthropic API (or AWS Bedrock), for reading emails only |
