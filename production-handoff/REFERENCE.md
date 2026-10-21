# Reference: specs by system

The detailed specs behind the [roadmap](ROADMAP.md): every field, script, endpoint and setting, grouped by system. Item numbers (W1, S1, N8, E2…) are the ones the roadmap steps refer to. The building blocks in the subfolders implement these specs as skeletons.

**Owners:** WC = WooCommerce/WordPress developer · SF = Salesforce admin/developer · NS = NetSuite administrator/SuiteScript developer · INT = integration engineer.
**Sizes:** S = up to 2 days · M = 3–5 days · L = 1–2 weeks.
**"Verify"** marks something we couldn't confirm from outside Perennials; each one is a decision in [DECISIONS.md](DECISIONS.md).

---

## 1. Target architecture

```
WooCommerce ──order.created webhook (HMAC)──┐
Gmail quotes@perennialsfabrics.com ──watch → Pub/Sub push (OIDC)─┤
Salesforce Flow ──approval callback─────────┤
                                            ▼
                 API Gateway → ingest Lambda → SQS FIFO (group = customer email) → worker Lambda
                                                                │
                      ┌──────────────── workflow (ported from s2q/workflow.py) ───────────────┐
                      │ extract → identify → qualify → act → escalate                          │
                      └──────┬───────────────────────────┬─────────────────────────┬──────────┘
                             ▼                           ▼                         ▼
                  SalesforceCRM adapter        NetSuiteERP adapter        Postgres: requests,
                  (REST, Composite, Apex REST) (REST record, SuiteQL,     audit_log, reviews
                                                RESTlet)
```

- **Why FIFO grouped by customer email:** requests from the same customer must be handled in order. A revision ("make that 90 yds") has to see the hold from the earlier quote, and a second sample request has to see the lead created by the first. Requests from different customers still run in parallel.
- **Idempotency:** the key is the WooCommerce order id or the Gmail message id. It is stored with a unique constraint in Postgres and also written to the Salesforce Lead as an external id. If the same webhook is delivered twice, nothing gets created twice.
- **Failures:** SQS retries three times, then the message goes to a dead-letter queue, which raises a CloudWatch alarm.

---

## 2. WooCommerce (owner: WC)

| # | Change | Detail | Size |
|---|---|---|---|
| W1 | **SKU audit.** Every variation's SKU equals the NetSuite item id. | Export all variation SKUs and diff them against the NetSuite item list (INT provides the script). Any mismatch is a sample or quote that can't be fulfilled automatically. | S |
| W2 | **Save cart fields as order line-item meta under fixed keys.** | Small mu-plugin on `woocommerce_checkout_create_order_line_item`. It copies the fields the product page already posts (`sampleProjectType[]`, `length`, `lengthUnit`, `dateNeeded`, `cfa[]`, `projectName`, `projectType[]`, comment) to the keys below. | M |
| W3 | **Order webhook.** | WooCommerce → Settings → Advanced → Webhooks. Topic **Order created**, delivery URL `https://<api>/webhooks/woocommerce`, plus a secret. WooCommerce signs each delivery in `X-WC-Webhook-Signature` (base64 HMAC-SHA256 of the body). | S |
| W4 | **Logged-in customers.** | If samples stay behind a trade login (*Verify*), save `_sf_contact_id` as WordPress user meta once the contact is matched. That makes matching exact on repeat orders. | S |
| W5 | **Discontinued items.** | Hide "Add Sample" on variations the ERP marks discontinued (synced as a product attribute). The workflow also enforces this, as defence in depth. | S |

**Line-item meta contract** (what the service reads):

| Key | Values | From the product page |
|---|---|---|
| `_s2q_line_type` | `sample` \| `quote` | which button was used |
| `_s2q_project_type` | `residential` \| `hospitality` | Project Type radio |
| `_s2q_length` / `_s2q_length_unit` | number / `yards` \| `feet` \| `meters` | Length + unit |
| `_s2q_date_needed` | ISO date | Date Needed |
| `_s2q_cfa` | `requested` \| `waived` | CFA radio |
| `_s2q_project_name` | text | Project Name |
| `_s2q_comment` | text | Comment/Sidemark |

The order's `customer_note` is the order note. Billing name, company and email give the contact details.

---

## 3. Salesforce (owner: SF)

### 3.1 Fields and picklists

| Object.Field | Type | Purpose |
|---|---|---|
| `Lead.Source_Request_Id__c` | Text(64), External Id, Unique | Idempotency: the WooCommerce order id or Gmail message id |
| `Lead.Qualification_Reason__c` | Long Text | Why the lead was qualified or not: account status for known accounts, or the rep's decision for new senders |
| `Lead.Project_Type__c` | Picklist: Residential, Hospitality | From the cart |
| `Lead.Project_Name__c` | Text(255) | Becomes the opportunity name |
| `Lead.Status` | add **Needs Review**, **Disqualified** | Qualification outcomes |
| `Contact.Alternate_Email__c` | Email (or a related list if more than one) | Same person on a second address (the WEB-003 case) |
| `Account.NetSuite_Customer_Id__c` | Text, External Id | Link to the NetSuite customer |
| `Account.Trade_Status__c` | Picklist: Trade, Do Not Sell | Drives qualification. *Verify* where Do Not Sell is kept today |
| `Opportunity.Sample_Order_Ids__c` | Long Text, or a child object `Sample_Order__c` | NetSuite sample order numbers |
| `Quote.Status` | add **Pending Rep Review**, **Superseded**, **Rejected** | Review and revisions |
| `Quote.Version__c` | Number | v1, v2… (a revision supersedes the earlier version) |
| `Quote.Review_Flags__c` | Long Text | The reasons a quote needs a person (PoC `flags`) |
| `Quote.Budgetary__c` | Checkbox | Budgetary quotes place no hold |
| `Quote.NetSuite_Hold_SO__c` / `Quote.Hold_Expires__c` | Text / Date | The ERP hold (read-only in Salesforce) |
| `Quote.CFA_Order__c` | Text | NetSuite CFA cutting order |
| `QuoteLineItem.Dye_Lots__c` | Text | e.g. `L-2401 52 yd + L-2417 35 yd` |
| `QuoteLineItem.Requested_Yards__c` | Number | When less than requested is quoted (shortage or discontinued) |
| `Task.Drafted_Message__c` | Long Text | The customer email the service drafted for this review (sent by **Send question** or on approval) |
| `Task.Decision__c` | Picklist: Qualify, Approve, Send question, Reject | Set by the Task quick actions; fires the callback Flow (S6) |

### 3.2 Configuration and automation

| # | Change | Detail | Size |
|---|---|---|---|
| S1 | **Products and price book.** | QuoteLineItem needs a PricebookEntry, so each NetSuite item must exist as a `Product2` (ProductCode = SKU) with a standard-price-book entry at list price. A nightly sync from NetSuite (INT) keeps them current. Net price goes in `UnitPrice`, and the discount is recorded on the line. | M |
| S2 | **Lead convert endpoint.** | The REST API has no lead convert call. Add a small Apex REST class, `/services/apexrest/s2q/convertLead`, that wraps `Database.convertLead` and can convert into an existing Account/Contact (the PoC's `convert_lead`). | S |
| S3 | **Duplicate and matching rules.** | A backstop for the service's own matching: email exact, then email domain + name, then company name. | S |
| S4 | **Review queue.** | Queue **Sample-to-Quote Review**. The service creates `Task` records (Subject = reason, WhatId = Lead or Quote) assigned to the queue. **Every new sender gets a qualification Task** with two actions, Qualify / Reject; approving runs the waiting sample order or quote. | S |
| S5 | **Approval process: quotes.** | On Quote: entry criteria `Status = Pending Rep Review`. Step 1 is the account owner. Step 2, a manager, applies when `GrandTotal > 20000` (PoC setting `manager_approval_over`; [decision D6](DECISIONS.md)). | M |
| S6 | **Approval callback.** | A record-triggered Flow fires when a Quote is approved or rejected, or a review Task is closed. It runs an **HTTP Callout** action (Named Credential → `https://<api>/callbacks/salesforce`) with `{record_id, decision, user}`. The service then does what was waiting: sends the quote, or places the samples. | M |
| S7 | **Quote PDF and email.** | A quote template for the PDF. Each review Task also stores the drafted customer message (Task description, or a `Drafted_Message__c` long-text field), and a **Send question** quick action on the Task calls the service. The service sends the customer email through the standard `emailSimple` action (`/services/data/vXX.X/actions/standard/emailSimple`) from an org-wide address (quotes@perennialsfabrics.com), so every email is logged on the Contact. | M |
| S8 | **Integration user and access.** | A Salesforce Integration user licence, an External Client App (OAuth 2.0 JWT bearer) and a permission set: CRUD on Lead, Contact, Account, Opportunity, Quote, QuoteLineItem, Task; Apex class access for S2. | S |

---

## 4. NetSuite (owner: NS)

| # | Change | Detail | Size |
|---|---|---|---|
| N1 | **Lot-numbered items.** | Each fabric colorway is a lot-numbered inventory item, and each dye lot is a lot number with quantity on hand. *Verify* that the feature is enabled and dye lots are already tracked this way. | (exists?) |
| N2 | **Item fields.** | `custitem_s2q_lifecycle` (Active / Discontinued / Backorder) and `custitem_s2q_backorder_eta` (Date). Alternatively, derive the ETA from open purchase orders. | S |
| N3 | **Customer link.** | Set `externalId` = Salesforce Account Id on customers the service creates. Backfill existing customers ([roadmap step 1.2](ROADMAP.md#phase-1-clean-the-data)). | S |
| N4 | **Pricing rules as a custom record.** | Custom record `customrecord_s2q_pricing_rule` (trade %, volume tiers, cut fee, cut-fee threshold, max samples, quote validity days, hold days). Merchandising edits it. This replaces the PoC reading the Pricing Rules tab. | S |
| N5 | **Pricing RESTlet.** | SuiteScript 2.1 RESTlet `customscript_s2q_price`. Input `{sku, yards, is_trade}`, output `{list_price, trade_discount, volume_discount, unit_price, cut_fee, line_total}`. Port it from `s2q/pricing.py`. Volume tiers are **trade only and add to** the trade discount (15% + 5% = 20%). Cut fee is $25 per line under 5 yd. Keep the Python version as the test oracle. | M |
| N6 | **Lot availability.** | SuiteQL (`POST /services/rest/query/v1/suiteql`) that returns, per lot, on hand and committed for a SKU. *Verify* which record holds that in their account (inventory number / inventory balance). | S |
| N7 | **Sales order forms.** | Custom forms **S2Q Sample** ($0 price level, memo-swatch line) and **S2Q CFA** ($0, one cutting per held lot). Body fields: `custbody_s2q_type` (Sample / Hold / CFA), `custbody_s2q_sf_quote_id`, `custbody_s2q_request_id`, `custbody_s2q_hold_expires`. | M |
| N8 | **Hold mechanism (decision).** | A *Pending Approval* sales order does not commit inventory by default. Choose one: **(a)** an approved sales order on a "Quote Hold" form with lot-level inventory detail, so the lots really are committed; or **(b)** an inventory transfer of the lots into a **HOLD** location or bin. The adapter supports either; (a) is simpler to reverse. *Verify* with the NetSuite admin ([decision D1](DECISIONS.md)). | M |
| N9 | **Hold expiry.** | A Map/Reduce script runs daily. It finds Hold orders where `custbody_s2q_hold_expires < today` and are still open, closes the lines (or transfers stock back), and writes the result back to Salesforce through the service. | M |
| N10 | **Integration record and role.** | OAuth 2.0 client credentials (M2M, certificate) on a dedicated role: customer create/edit, sales order create/edit/close, SuiteQL, RESTlet execute, item view. | S |

---

## 5. Integration service (owner: INT)

### 5.1 Endpoints

| Endpoint | Auth | Does |
|---|---|---|
| `POST /webhooks/woocommerce` | Verify `X-WC-Webhook-Signature` | Split the order into a sample request and/or a quote request (as in `demo/site.py`) and enqueue. Respond 200 within the WooCommerce timeout. |
| `POST /webhooks/gmail` | Verify the Pub/Sub OIDC token | Call `users.history.list` from the last stored historyId, fetch new messages, and enqueue each one with its message id. |
| `POST /callbacks/salesforce` | Named-credential header or JWT | An approve/reject decision. Runs `Workflow.approve` / `reject` (deferred action). |
| EventBridge daily | none | Renew the Gmail `users.watch` (it expires after 7 days); reconcile Salesforce and NetSuite holds. |
| EventBridge nightly | none | NetSuite item → Salesforce `Product2`/PricebookEntry sync (S1) and WooCommerce discontinued attribute (W5). |

### 5.2 From PoC to production, file by file

| PoC file | Production | Change |
|---|---|---|
| `s2q/workflow.py` | `workflow/` | Keep the logic and stages. Move state (`results`, `reviews`) to Postgres. `approve`/`reject` are triggered by the Salesforce callback. |
| `s2q/extract.py` | `intake/` | Keep `CartIntake` (now reads the WooCommerce meta from §2) and the email extractors. The LLM catalog comes from a cached NetSuite item list. Keep catalog validation and the rules cross-check. |
| `s2q/identity.py` | `identity/` | Same matching order (email → converted lead → domain + name → domain → company), implemented as SOQL queries. |
| `s2q/qualify.py` | `policy/` | Unchanged policy: known accounts decided from `Account.Trade_Status__c`; every new sender goes to a qualification Task. |
| `s2q/pricing.py` | NetSuite RESTlet (N5) | Pricing moves into NetSuite. The Python stays as the test oracle. |
| `s2q/emails.py` | `emails/` | Same templates; numbers only from NetSuite. Sent through Salesforce `emailSimple` (S7). |
| `s2q/adapters/crm.py` `MockCRM` | `SalesforceCRM` | Same method names. `create_lead` is an upsert on `Source_Request_Id__c`; `convert_lead` calls the Apex REST (S2); `create_quote` uses a Composite request (Quote + QuoteLineItems); `create_task` creates a Task in the S4 queue. |
| `s2q/adapters/erp.py` `MockERP` | `NetSuiteERP` | `items`/`lots_for` call SuiteQL (N6); `price` calls the RESTlet (N5); `allocate` keeps the same single-lot-first rule; sample, hold and CFA orders are created with the forms in N7/N8; `release_reservation` closes lines and `reinstate_reservation` re-opens them if a revision falls through. |
| `s2q/audit.py` | Postgres `audit_log` | One row per external call (request id, system, action, payload hash, response id, status). |
| `s2q/data.py` | removed | Live reads replace the workbook. Pricing comes from N4. |
| `demo/` (app, pages, `site.py`, `baseline.py`, data) | demo only | Not shipped. Before production, make the small `s2q/` refactors listed in [`integration-service/README.md`](integration-service/README.md#refactors-to-make-in-s2q-before-production). |

### 5.3 Data store (Postgres)

- `requests(id pk, source, source_id unique, customer_email, payload jsonb, status, created_at)`
- `audit_log(id, request_id fk, system, action, external_id, status, error, created_at)`
- `reviews(id, request_id fk, sf_record_id, reason, action, payload jsonb, status, decided_by, decided_at)`
- `gmail_state(mailbox pk, history_id, watch_expires_at)`

### 5.4 Non-functional

- **Secrets** in Secrets Manager: Salesforce JWT key, NetSuite certificate, WooCommerce webhook secret, Anthropic key, Gmail service account.
- **Gmail access:** a service account with domain-wide delegation, scope `gmail.modify` (read, plus label messages as processed).
- **AI guardrails, already in the PoC:** structured outputs (`output_config.format` JSON schema; forced `tool_choice` is rejected by current models); server-side refusal fallbacks; output checked against the item list; rules cross-check, with any disagreement sent to review; the model never sets price or qualification. Log the model id and prompt version per request.
- **Observability:** dead-letter queue alarm, review-queue age alarm (for example, a review open longer than 4 business hours), daily hold-reconciliation report.

---

## 6. Email (owners: INT + Google Workspace admin)

| # | Change | Size |
|---|---|---|
| E1 | Set up quotes@perennialsfabrics.com as a Google Group or shared mailbox; grant the service account delegated access (§5.4). | S |
| E2 | Create a Pub/Sub topic `s2q-gmail`, give `gmail-api-push@system.gserviceaccount.com` publish rights, and add a push subscription to `/webhooks/gmail`. | S |
| E3 | Call `users.watch` on quotes@perennialsfabrics.com with the INBOX label; renew it daily (§5.1). | S |
| E4 | Send replies through Salesforce from the org-wide quotes@perennialsfabrics.com address, so threads stay in one place and are logged on the Contact. | S (with S7) |

---

## 7. MCP servers: where they fit

Salesforce and NetSuite both ship official MCP servers, which let an AI client such as Claude read and change their data. As of October 2026:

| | NetSuite AI Connector Service | Salesforce Hosted MCP Servers |
|---|---|---|
| Status | Available, no extra license (the AI client may need a paid plan) | Generally available since April 2026; Enterprise Edition and above |
| Built-in tools | MCP Standard Tools SuiteApp: create / get / update records, record-type metadata, saved searches, reports, custom SuiteQL | Record read / create / update / delete, Flows, named queries, prompt templates |
| Our own tools | Custom tool scripts (SuiteScript 2.1, `@NScriptType CustomTool`), deployed with SDF | Apex actions, Apex REST and Flows published as hosted tools |
| Login | OAuth 2.0 authorization code with PKCE only: a person signs in through a browser. The Administrator role isn't allowed | OAuth 2.0 with PKCE only, through an External Client App: a person signs in |
| Runs as | The signed-in user's NetSuite role | The signed-in user, with field-level security and sharing rules |

### The pipeline stays on the regular APIs
1. **No way for a service to log in.** Both servers need a person to sign in. The pipeline runs unattended (a webhook at 2am still has to create the sample order), so it uses the service logins in §5.4: Salesforce's JWT bearer flow for an integration user, and NetSuite's certificate-based OAuth.
2. **Deterministic in the middle.** Claude reads emails; pricing, dye-lot holds and decisions are tested code (`s2q/`). Letting a model choose which records to write through MCP would make the money and inventory steps probable instead of guaranteed.
3. **Volume.** Nightly product sync and the account backfill are bulk work, which suits the REST and SuiteQL APIs.

### Where MCP adds value
| Use | Who | How | When |
|---|---|---|---|
| **Rep assistant** for the review queue: "what has Ruiz Interiors ordered?", "which lot covers 45 yards?", "why was this quote flagged?" | Reps | Claude connected to both servers, as the rep, read-only at first (D12) | Later, after phase 4 |
| **One implementation, two callers:** the pricing RESTlet (N5) and lead convert (S2) also published as MCP tools (`s2q_price_quote` as a NetSuite custom tool, lead convert as a hosted Apex tool) | NS, SF | Put the logic in a shared SuiteScript module / Apex class; the RESTlet and the MCP tool are thin wrappers | With 4.2 and 3.1 |
| **Build and clean-up help:** field definitions for the adapters, SuiteQL for the SKU audit (1.1) and the unmatched accounts (1.2), daily shadow comparisons (2.5) | INT, NS | Claude with the NetSuite server, as a non-admin role scoped to the sandbox | Phases 0–2 |

Setup notes: in NetSuite, enable the AI Connector Service, install the MCP Standard Tools SuiteApp, and create an integration record (public client, authorization code grant, AI Connector Service scope) and a custom role. In Salesforce, create an External Client App for the MCP client and choose which tools each server exposes. Salesforce's DX MCP server is for developers only and reaches end of life on November 2, 2026 (R11). Third-party MCP gateways for NetSuite exist, but they add a vendor in the ERP data path.

Sources: [NetSuite AI Connector Service FAQ](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/article_4160616848.html) · [SuiteScript Custom Tool script type](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/article_1185045525.html) · [Salesforce Hosted MCP Servers](https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide) · [Custom Apex as a hosted MCP tool](https://developer.salesforce.com/blogs/2026/05/expose-custom-apex-as-a-hosted-mcp-tool-for-agents)
