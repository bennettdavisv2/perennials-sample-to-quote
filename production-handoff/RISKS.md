# Risks

The things most likely to go wrong, and where the [roadmap](ROADMAP.md) deals with each one. The order of the phases is mostly about retiring these early.

| # | Risk | Impact | How we lower it | Retired by |
|---|---|---|---|---|
| R1 | **NetSuite holds don't actually commit inventory.** A pending sales order doesn't reserve stock by default, so fabric quoted as held could be sold to someone else. | High: promised fabric isn't there | Decide the mechanism up front (D1) and prove it in the sandbox: held yards must show as committed | Phase 0 (decision), 5.1 (built) |
| R2 | **Quote lines can't be created in Salesforce.** Each line needs the item as a Product with a price-book entry. | Medium: blocks quoting | Nightly product sync from NetSuite (S1), built in the sandbox during shadow mode | 4.1 |
| R3 | **Data doesn't line up across systems:** SKUs that don't match NetSuite items, accounts not linked to customers. | High, and silent | SKU audit and customer backfill before anything is written | Phase 1 |
| R4 | **Emails are read wrongly** on real messages (new wording, quoted threads, attachments). | Medium: wrong quotes | Two weeks of shadow mode with a 95% agreement bar; catalog validation; rules cross-check; anything uncertain goes to a rep | 2.5, then 4.6 (every quote reviewed) |
| R5 | **Duplicate records** from webhook retries or two messages from one customer arriving together. | Medium: duplicate leads or holds | Idempotency key per message; a queue that processes one customer's requests in order; open-lead dedupe | 2.3 |
| R6 | **The rep queue backs up.** Every new sender now needs a person to qualify them. | Medium: slower than today | Measure qualification volume in shadow mode; alarm on reviews older than 4 business hours; D8 decides who works the queue | 2.5, 3.2 |
| R7 | **Missed emails** if the Gmail watch lapses (it expires after 7 days). | Medium: lost quote requests | Daily watch renewal; catch-up from the last processed history id; daily reconciliation | 2.2 |
| R8 | **Claude unavailable or slow.** | Low | Automatic fallback to the rules reader, shown in the logs; model pinned; usage monitored | 2.3 |
| R9 | **Spoofed webhooks or leaked credentials.** | High | Signature check on WooCommerce, OIDC token on Gmail push, secrets in Secrets Manager, least-privilege integration users | 0.3, 2.3 |
