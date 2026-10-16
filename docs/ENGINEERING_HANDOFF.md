# Engineering handoff: sample-to-quote integration

This is the list of changes engineering would make to put the PoC into production at Perennials. It is organised by system, so each owner gets their own checklist. Every rule referenced here is implemented and tested in the PoC (`s2q/`). The PoC is the reference behaviour, and its 26 tests become the acceptance tests.

**Assumed stack**

| Layer | Choice |
|---|---|
| Website | WooCommerce on WordPress (confirmed on perennialsfabrics.com: each colorway is a product variation) |
| CRM | Salesforce Sales Cloud, Enterprise edition or above, with Quotes enabled |
| ERP | NetSuite with Lot Numbered Inventory (one lot number = one dye lot) |
| Integration | New Python service on AWS: API Gateway, Lambda, SQS FIFO, RDS Postgres, Secrets Manager, EventBridge |
| Inbound email | Google Workspace: quotes@ watched through the Gmail API, with Pub/Sub push |
| AI | Claude through the Anthropic API (or AWS Bedrock), used for email intake only |

**Owners:** WC = WooCommerce/WordPress developer · SF = Salesforce admin/developer · NS = NetSuite administrator/SuiteScript developer · INT = integration engineer.
**Sizes:** S = up to 2 days · M = 3–5 days · L = 1–2 weeks.

**"Verify"** marks something we could not confirm from outside Perennials. Each one is also listed in [§8 Open questions](#8-open-questions-for-perennials).

---

## 1. Target architecture

```
WooCommerce ──order.created webhook (HMAC)──┐
Gmail quotes@ ──watch → Pub/Sub push (OIDC)─┤
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
| `Lead.Qualification_Reason__c` | Long Text | Why the policy qualified, disqualified or flagged the lead (shown to the rep) |
| `Lead.Project_Type__c` | Picklist: Residential, Hospitality | From the cart |
| `Lead.Project_Name__c` | Text(255) | Becomes the opportunity name |
| `Lead.Status` | add **Needs Review**, **Nurture – Non-trade**, **Disqualified** | Qualification outcomes |
| `Contact.Alternate_Email__c` | Email (or a related list if more than one) | Same person on a second address (the WEB-003 case) |
| `Account.NetSuite_Customer_Id__c` | Text, External Id | Link to the NetSuite customer |
| `Account.Trade_Status__c` | Picklist: Trade, Consumer, Do Not Sell | Drives qualification. *Verify* where Do Not Sell is kept today |
| `Opportunity.Sample_Order_Ids__c` | Long Text, or a child object `Sample_Order__c` | NetSuite sample order numbers |
| `Quote.Status` | add **Pending Rep Review**, **Superseded**, **Rejected** | Review and revisions |
| `Quote.Version__c` | Number | v1, v2… (a revision supersedes the earlier version) |
| `Quote.Review_Flags__c` | Long Text | The reasons a quote needs a person (PoC `flags`) |
| `Quote.Budgetary__c` | Checkbox | Budgetary quotes place no hold |
| `Quote.NetSuite_Hold_SO__c` / `Quote.Hold_Expires__c` | Text / Date | The ERP hold (read-only in Salesforce) |
| `Quote.CFA_Order__c` | Text | NetSuite CFA cutting order |
| `QuoteLineItem.Dye_Lots__c` | Text | e.g. `L-2401 52 yd + L-2417 35 yd` |
| `QuoteLineItem.Requested_Yards__c` | Number | When less than requested is quoted (shortage or discontinued) |

### 3.2 Configuration and automation

| # | Change | Detail | Size |
|---|---|---|---|
| S1 | **Products and price book.** | QuoteLineItem needs a PricebookEntry, so each NetSuite item must exist as a `Product2` (ProductCode = SKU) with a standard-price-book entry at list price. A nightly sync from NetSuite (INT) keeps them current. Net price goes in `UnitPrice`, and the discount is recorded on the line. | M |
| S2 | **Lead convert endpoint.** | The REST API has no lead convert call. Add a small Apex REST class, `/services/apexrest/s2q/convertLead`, that wraps `Database.convertLead` and can convert into an existing Account/Contact (the PoC's `convert_lead`). | S |
| S3 | **Duplicate and matching rules.** | A backstop for the service's own matching: email exact, then email domain + name, then company name. | S |
| S4 | **Review queue.** | Queue **Sample-to-Quote Review**. The service creates `Task` records (Subject = reason, WhatId = Lead or Quote) assigned to the queue. | S |
| S5 | **Approval process: quotes.** | On Quote: entry criteria `Status = Pending Rep Review`. Step 1 is the account owner. Step 2, a manager, applies when `GrandTotal > 20000` (PoC `HIGH_VALUE`). | M |
| S6 | **Approval callback.** | A record-triggered Flow fires when a Quote is approved or rejected, or a review Task is closed. It runs an **HTTP Callout** action (Named Credential → `https://<api>/callbacks/salesforce`) with `{record_id, decision, user}`. The service then does what was waiting: sends the quote, or places the samples. | M |
| S7 | **Quote PDF and email.** | A quote template for the PDF. Each review Task also stores the drafted customer message (Task description, or a `Drafted_Message__c` long-text field), and a **Send question** quick action on the Task calls the service. The service sends the customer email through the standard `emailSimple` action (`/services/data/vXX.X/actions/standard/emailSimple`) from an org-wide address (quotes@), so every email is logged on the Contact. | M |
| S8 | **Integration user and access.** | A Salesforce Integration user licence, an External Client App (OAuth 2.0 JWT bearer) and a permission set: CRUD on Lead, Contact, Account, Opportunity, Quote, QuoteLineItem, Task; Apex class access for S2. | S |

---

## 4. NetSuite (owner: NS)

| # | Change | Detail | Size |
|---|---|---|---|
| N1 | **Lot-numbered items.** | Each fabric colorway is a lot-numbered inventory item, and each dye lot is a lot number with quantity on hand. *Verify* that the feature is enabled and dye lots are already tracked this way. | (exists?) |
| N2 | **Item fields.** | `custitem_s2q_lifecycle` (Active / Discontinued / Backorder) and `custitem_s2q_backorder_eta` (Date). Alternatively, derive the ETA from open purchase orders. | S |
| N3 | **Customer link.** | Set `externalId` = Salesforce Account Id on customers the service creates. Backfill existing customers (§7). | S |
| N4 | **Pricing rules as a custom record.** | Custom record `customrecord_s2q_pricing_rule` (trade %, volume tiers, cut fee, cut-fee threshold, max samples, quote validity days, hold days). Merchandising edits it. This replaces the PoC reading the Pricing Rules tab. | S |
| N5 | **Pricing RESTlet.** | SuiteScript 2.1 RESTlet `customscript_s2q_price`. Input `{sku, yards, is_trade}`, output `{list_price, trade_discount, volume_discount, unit_price, cut_fee, line_total}`. Port it from `s2q/pricing.py`. Volume tiers are **trade only and add to** the trade discount (15% + 5% = 20%). Cut fee is $25 per line under 5 yd. Keep the Python version as the test oracle. | M |
| N6 | **Lot availability.** | SuiteQL (`POST /services/rest/query/v1/suiteql`) that returns, per lot, on hand and committed for a SKU. *Verify* which record holds that in their account (inventory number / inventory balance). | S |
| N7 | **Sales order forms.** | Custom forms **S2Q Sample** ($0 price level, memo-swatch line) and **S2Q CFA** ($0, one cutting per held lot). Body fields: `custbody_s2q_type` (Sample / Hold / CFA), `custbody_s2q_sf_quote_id`, `custbody_s2q_request_id`, `custbody_s2q_hold_expires`. | M |
| N8 | **Hold mechanism (decision).** | A *Pending Approval* sales order does not commit inventory by default. Choose one: **(a)** an approved sales order on a "Quote Hold" form with lot-level inventory detail, so the lots really are committed; or **(b)** an inventory transfer of the lots into a **HOLD** location or bin. The adapter supports either; (a) is simpler to reverse. *Verify* with the NetSuite admin. | M |
| N9 | **Hold expiry.** | A Map/Reduce script runs daily. It finds Hold orders where `custbody_s2q_hold_expires < today` and are still open, closes the lines (or transfers stock back), and writes the result back to Salesforce through the service. | M |
| N10 | **Integration record and role.** | OAuth 2.0 client credentials (M2M, certificate) on a dedicated role: customer create/edit, sales order create/edit/close, SuiteQL, RESTlet execute, item view. | S |

---

## 5. Integration service (owner: INT)

### 5.1 Endpoints

| Endpoint | Auth | Does |
|---|---|---|
| `POST /webhooks/woocommerce` | Verify `X-WC-Webhook-Signature` | Split the order into a sample request and/or a quote request (as in `s2q/site.py`) and enqueue. Respond 200 within the WooCommerce timeout. |
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
| `s2q/qualify.py` | `policy/` | Unchanged policy table. Do Not Sell is read from `Account.Trade_Status__c`. |
| `s2q/pricing.py` | NetSuite RESTlet (N5) | Pricing moves into NetSuite. The Python stays as the test oracle. |
| `s2q/emails.py` | `emails/` | Same templates; numbers only from NetSuite. Sent through Salesforce `emailSimple` (S7). |
| `s2q/adapters/crm.py` `MockCRM` | `SalesforceCRM` | Same method names. `create_lead` is an upsert on `Source_Request_Id__c`; `convert_lead` calls the Apex REST (S2); `create_quote` uses a Composite request (Quote + QuoteLineItems); `create_task` creates a Task in the S4 queue. |
| `s2q/adapters/erp.py` `MockERP` | `NetSuiteERP` | `items`/`lots_for` call SuiteQL (N6); `price` calls the RESTlet (N5); `allocate` keeps the same single-lot-first rule; sample, hold and CFA orders are created with the forms in N7/N8; `release_reservation` closes lines. |
| `s2q/audit.py` | Postgres `audit_log` | One row per external call (request id, system, action, payload hash, response id, status). |
| `s2q/data.py` | removed | Live reads replace the workbook. Pricing comes from N4. |
| `s2q/site.py`, `s2q/baseline.py`, `ui/`, `app.py` | demo only | Not shipped. |

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
| E1 | Set up quotes@ as a Google Group or shared mailbox; grant the service account delegated access (§5.4). | S |
| E2 | Create a Pub/Sub topic `s2q-gmail`, give `gmail-api-push@system.gserviceaccount.com` publish rights, and add a push subscription to `/webhooks/gmail`. | S |
| E3 | Call `users.watch` on quotes@ with the INBOX label; renew it daily (§5.1). | S |
| E4 | Send replies through Salesforce from the org-wide quotes@ address, so threads stay in one place and are logged on the Contact. | S (with S7) |

---

## 7. Data, testing and rollout

**Data backfill (INT + SF + NS)**
- Match existing Salesforce Accounts to NetSuite customers and fill both `NetSuite_Customer_Id__c` and `externalId`. Send unmatched records to a cleanup list.
- Load the Do Not Sell list into `Account.Trade_Status__c`.
- Run the SKU audit (W1) before go-live.

**Testing**
- Use a Salesforce sandbox, a NetSuite sandbox and a WooCommerce staging site, with the service deployed per environment.
- **Acceptance suite:** the 21 workbook rows with their expected outcomes (README "Interesting rows", `tests/`), replayed against the sandboxes. Add the live demo cases: a sample attached to an existing opportunity; a clean email quote sent automatically; "the canvas" settled by sample history; "the linen" producing one question; a 90 ft quote line with CFA requested.

**Rollout**

| Phase | What runs | Exit criteria |
|---|---|---|
| 0. Setup (≈1 week) | Decisions in §8, sandboxes, access, field metadata | All Verify items answered |
| 1. Shadow (≈2 weeks) | The service reads live webhooks and email and writes **only to Postgres**. Reps work as today. Compare daily. | At least 95% agreement on SKU and quantity extraction; no wrong-account matches |
| 2. Write, with review | Leads, opportunities and sample orders are written automatically. **Every** quote goes to review before sending. | Reps approve at least 90% of quotes unchanged |
| 3. Auto-send | Quotes with no flags are sent automatically with a hold. Flags and > $20k still go to review. | Ongoing monitoring: review-queue age, DLQ, hold reconciliation |

**Rough total:** about 6–8 weeks of engineering for one integration engineer, with part-time Salesforce and NetSuite admins. Most of the uncertainty is in N8 (the hold mechanism) and S1 (product sync).

---

## 8. Open questions for Perennials

| # | Question | Assumption in the PoC |
|---|---|---|
| 1 | Do samples require a trade account login, or is guest checkout allowed? | Guest checkout allowed (README assumption 19). With login, matching uses `_sf_contact_id` (W4). |
| 2 | Are dye lots tracked as lot numbers in NetSuite today? | Yes (N1) |
| 3 | How should a quote hold work in NetSuite: committed sales order or hold location? | Undecided; the adapter supports both (N8) |
| 4 | Where is Do Not Sell kept today? | An account-level status (`Trade_Status__c`) |
| 5 | Is there already a Salesforce–NetSuite connector (Celigo, Breadwinner…)? | No. If there is, the customer link (N3) and product sync (S1) reuse it. |
| 6 | What dollar amount needs manager approval? | $20,000 (S5) |
| 7 | Are pricing rules really additive (15% + 5%) rather than compounding? | Additive (README assumption 1) |
| 8 | Who owns the review queue: the account owner, or a shared inside-sales queue? | The shared queue, then the account owner (S4/S5) |
| 9 | Is Google Workspace the email platform for quotes@? | Yes (§6) |
