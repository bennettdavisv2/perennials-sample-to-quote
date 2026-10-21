**Owners:** WC = WooCommerce/WordPress developer · SF = Salesforce admin/developer · NS = NetSuite administrator/SuiteScript developer · INT = integration engineer · Ops = sales ops / the sales team.

## At a glance

| Phase | Goal | Weeks | Writes to Salesforce / NetSuite? |
|---|---|---|---|
| [0. Decide and set up](#phase-0-decide-and-set-up) | Blocking decisions answered, sandboxes and access in place, core refactors done | 1 | No |
| [1. Clean the data](#phase-1-clean-the-data) | SKUs match, accounts and customers linked, fields deployed | 2 | Metadata and backfill only |
| [2. Shadow mode](#phase-2-shadow-mode-read-only) | Live traffic processed end to end, results compared with what reps did | 3–5 | **No** |
| [3. Leads and samples](#phase-3-leads-and-samples) | Leads, qualification tasks and sample orders written automatically | 5–6 | Yes: leads, tasks, sample orders |
| [4. Quotes, all reviewed](#phase-4-quotes-all-reviewed) | Quotes priced and created; **every** quote approved by a rep | 6–7 | Yes: quotes |
| [5. Holds](#phase-5-holds) | Dye-lot holds, CFA cuttings, daily hold expiry | 8 | Yes: inventory |
| [6. Auto-send](#phase-6-auto-send) | Clean quotes go out without a click | 9 | Yes |

**Critical path:** phases 0 → 1 → 2 are sequential. During shadow mode (weeks 4–5) the Salesforce and NetSuite work for phases 3–5 is built and tested in the sandboxes in parallel, so the later phases are mostly switch-ons. Rough total: **about 9 weeks** for one integration engineer, with part-time WooCommerce, Salesforce and NetSuite admins.

---

## Phase 0: Decide and set up

| Step | What | Owner | Depends on | Done when | Start from |
|---|---|---|---|---|---|
| 0.1 | Answer the blocking decisions: **D1** hold mechanism, **D2** existing connector, **D3** Do Not Sell, **D4** checkout login, **D5** lot tracking | Ops + NS + SF | — | Each answered and recorded in DECISIONS.md | [DECISIONS.md](DECISIONS.md) |
| 0.2 | Sandboxes: Salesforce sandbox, NetSuite sandbox, WooCommerce staging, AWS dev account | SF, NS, WC, INT | — | The service's dev environment can reach all three | — |
| 0.3 | Integration access and secrets: Salesforce integration user (S8), NetSuite role (N10), Gmail delegated access (E1), keys in Secrets Manager | SF, NS, INT | 0.2 | A smoke call authenticates to each sandbox | [REFERENCE §5.4](REFERENCE.md#54-non-functional) |
| 0.4 | Core refactors in `s2q/`: inject the adapters, lookups instead of lists, state in Postgres, real clock | INT | — | All tests pass with the mocks injected | [integration-service/README.md](integration-service/README.md#refactors-to-make-in-s2q-before-production) |

## Phase 1: Clean the data

Everything later refers to SKUs and customer links. Bad data here breaks things quietly, so fix it first.

| Step | What | Owner | Depends on | Done when | Start from |
|---|---|---|---|---|---|
| 1.1 | SKU audit: every WooCommerce variation SKU = a NetSuite item (W1) | WC + INT | 0.2 | Mismatch list is empty or ticketed | [woocommerce/WEBHOOK.md](woocommerce/WEBHOOK.md) |
| 1.2 | Link Salesforce accounts to NetSuite customers and backfill `NetSuite_Customer_Id__c` / `externalId` (N3). Reuse the connector if D2 says one exists. | INT + SF + NS | 0.3, D2 | Linked accounts reviewed; unmatched list cleaned up | [REFERENCE §4](REFERENCE.md#4-netsuite-owner-ns) |
| 1.3 | Load Do Not Sell into `Account.Trade_Status__c` | SF | D3 | Every known reseller / competitor is flagged | [REFERENCE §3.1](REFERENCE.md#31-fields-and-picklists) |
| 1.4 | Deploy the Salesforce fields and picklists | SF | 0.2 | Fields exist in the sandbox | [salesforce/](salesforce/) |
| 1.5 | NetSuite item fields (N2); confirm lot tracking (N1) | NS | D5 | Lifecycle field populated for every active item | [REFERENCE §4](REFERENCE.md#4-netsuite-owner-ns) |
| 1.6 | Pricing rules as a custom record (N4) | NS | — | Record matches the workbook's Pricing Rules tab | [netsuite/README.md](netsuite/README.md) |

## Phase 2: Shadow mode (read only)

Prove matching and email reading on real traffic with **zero risk**: the service reads everything and writes only to its own database. Reps work exactly as today.

| Step | What | Owner | Depends on | Done when | Start from |
|---|---|---|---|---|---|
| 2.1 | WooCommerce plugin and order webhook (W2, W3) | WC | 1.1 | A staging order delivers the meta keys in the webhook payload | [woocommerce/](woocommerce/) |
| 2.2 | Gmail watch on quotes@perennialsfabrics.com (E2, E3) | INT | 0.3 | A test email reaches `/webhooks/gmail` | [gmail/](gmail/) |
| 2.3 | Service skeleton: handlers, FIFO queue, worker, Postgres, idempotency, dead-letter alarm | INT | 0.4 | A duplicate webhook is processed once; a forced failure lands in the dead-letter queue and alarms | [integration-service/](integration-service/) |
| 2.4 | Read-only adapters: Salesforce lookups, NetSuite items and lots (N6) | INT | 1.2, 1.5 | For 20 sampled customers and items, answers match what the Salesforce / NetSuite screens show | [integration-service/adapters/](integration-service/adapters/) |
| 2.5 | **Run in shadow for 2 weeks;** compare daily with what reps actually did (the NetSuite MCP server and SuiteQL make the daily comparison an interactive check, §7) | INT + Ops | 2.1–2.4 | At least 95% agreement on SKU and quantity from emails; no wrong-customer matches; qualification volume measured (sizes the rep queue) | — |

## Phase 3: Leads and samples

The lowest-risk writes: no money and no inventory commitment. Reps feel the benefit first.

| Step | What | Owner | Depends on | Done when | Start from |
|---|---|---|---|---|---|
| 3.1 | Lead create / convert (S2) and duplicate rules (S3) | SF + INT | 1.4 | Replaying WEB-001 + WEB-003 gives one lead, with the second address recorded | [salesforce/…/S2QConvertLead.cls](salesforce/force-app/main/default/classes/S2QConvertLead.cls) |
| 3.2 | Review queue (S4), Task quick actions, and the callback Flow (S6) | SF + INT | 2.3 | Clicking **Qualify** on a task places the waiting sample order | [salesforce/README.md](salesforce/README.md) |
| 3.3 | Sample order form and creation (N7, Sample) | NS + INT | 1.2 | The sample order appears on the right customer with the right SKUs | [REFERENCE §4](REFERENCE.md#4-netsuite-owner-ns) |
| 3.4 | Sample confirmation email from Salesforce (S7 sample part, E4) | SF + INT | 0.3 | The email is logged on the Contact | [REFERENCE §3.2](REFERENCE.md#32-configuration-and-automation) |
| 3.5 | **Go live for sample requests** | All | 3.1–3.4 | The sample rows of the acceptance suite pass in the sandbox; Ops signs off | `tests/` |

## Phase 4: Quotes, all reviewed

Money is involved, so a person checks every quote until the numbers are trusted.

| Step | What | Owner | Depends on | Done when | Start from |
|---|---|---|---|---|---|
| 4.1 | Nightly product sync: NetSuite items → Salesforce Products and price book (S1); discontinued flag to WooCommerce (W5) | INT + SF | 1.5 | Every active SKU has a price-book entry | [REFERENCE §5.1](REFERENCE.md#51-endpoints) |
| 4.2 | Pricing RESTlet (N5); keep the logic in a library the rep assistant can reuse as an MCP custom tool (§7) | NS | 1.6, D7 | Matches `s2q/pricing.py` on its test cases and on 50 sampled lines | [netsuite/s2q_price_restlet.js](netsuite/s2q_price_restlet.js) |
| 4.3 | Quote creation, versions and flags in Salesforce | INT + SF | 4.1, 4.2 | Replaying EML-014 to EML-021 gives the expected quotes and versions | [integration-service/adapters/salesforce.py](integration-service/adapters/salesforce.py) |
| 4.4 | Approval process with the manager threshold (S5) | SF | 4.3, D6 | A quote over the threshold routes to a manager | [REFERENCE §3.2](REFERENCE.md#32-configuration-and-automation) |
| 4.5 | Quote PDF template and quote email (S7) | SF | 4.3 | The quote email and PDF are logged on the Contact | [REFERENCE §3.2](REFERENCE.md#32-configuration-and-automation) |
| 4.6 | **Go live: every quote goes to a rep** | All | 4.1–4.5 | Over 2 weeks, reps approve at least 90% of quotes unchanged | — |

## Phase 5: Holds

The riskiest NetSuite piece, built once the hold mechanism (D1) is decided and pricing is trusted.

| Step | What | Owner | Depends on | Done when | Start from |
|---|---|---|---|---|---|
| 5.1 | Hold mechanism (N8): create, release and reinstate holds by dye lot | NS + INT | D1, 4.3 | Held yards show as committed in NetSuite; releasing returns them; a failed revision puts the hold back | [integration-service/adapters/netsuite.py](integration-service/adapters/netsuite.py) |
| 5.2 | CFA cutting order form (N7, CFA) | NS | 5.1 | A CFA request creates a cutting from the held lot | [REFERENCE §4](REFERENCE.md#4-netsuite-owner-ns) |
| 5.3 | Daily hold expiry (N9) and hold reconciliation | NS + INT | 5.1 | An expired test hold is released and Salesforce shows it | [netsuite/s2q_hold_expiry_mr.js](netsuite/s2q_hold_expiry_mr.js) |

## Phase 6: Auto-send

| Step | What | Owner | Depends on | Done when | Start from |
|---|---|---|---|---|---|
| 6.1 | Clean quotes (no flags, under the threshold) are sent automatically; everything else still goes to a rep | INT | 4.6, 5.3 | Two weeks with an empty dead-letter queue, reviews answered within 4 business hours, holds reconciled daily | — |

## Later

Valuable, but not needed to remove the manual handoffs:
- **The customer's decision:** an accept / decline link on the quote. Accept turns the hold into an order (Closed Won); decline or expiry releases it (Closed Lost).
- **Project-level opportunity matching:** a designer runs several jobs at once.
- **Extraction accuracy set:** about 100 labeled historical emails, to tune review thresholds from data.
- **Logged-in matching (W4):** if samples move behind a trade login (D4).
- **Rep assistant over MCP (D12):** Claude connected to Salesforce's hosted MCP server and NetSuite's AI Connector Service, running as the rep, to answer questions in the review queue ("what has this account ordered?", "which lot covers 45 yards?"). Publish the pricing script and lead convert as MCP tools so the assistant and the pipeline share one implementation. Read-only first. See [REFERENCE §7](REFERENCE.md#7-mcp-servers-where-they-fit).
