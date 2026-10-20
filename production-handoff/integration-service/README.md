# Integration service (AWS)

**Skeleton / spec.** These files define the service's shape, its endpoints and every external call. None of it has been deployed or run. The business logic it runs is the tested `s2q/` package at the repo root, unchanged.

| File | What it is |
|---|---|
| `handlers.py` | API Gateway endpoints: WooCommerce webhook (signature check), Gmail push, Salesforce approval callback. They authenticate, normalise and enqueue, with no business logic. |
| `worker.py` | SQS FIFO consumer: idempotency check, then `s2q.workflow` with real adapters; partial-batch failure reporting |
| `adapters/salesforce.py` | `SalesforceCRM`: same methods as `s2q/adapters/crm.py` `MockCRM`, each with its exact SOQL / REST call |
| `adapters/netsuite.py` | `NetSuiteERP`: same methods as `s2q/adapters/erp.py` `MockERP`, each with its REST / SuiteQL / RESTlet call |
| `schema.sql` | Postgres: requests (idempotency), audit_log, reviews, gmail_state |
| `template.yaml` | AWS SAM: HTTP API, two functions, FIFO queue + dead-letter queue + alarm |

`tests/test_handoff.py` checks that both adapters cover every method of their mock, so the interface can't drift.

## Refactors to make in `s2q/` before production
Small changes. The demo hides them because the mocks keep everything in memory.
1. **Inject the adapters.** `Workflow.__init__` builds `MockCRM` / `MockERP` from the workbook. Make `crm`, `erp`, the extractor and a state store constructor arguments; the demo passes the mocks.
2. **Lookups, not lists.** The workflow reads `crm.leads`, `crm.contacts`, `crm.opportunities`, `crm.quotes` and `erp.sales_orders` directly, which only works in memory. Replace them with `get_lead`, `get_contact`, `get_opportunity`, `get_quote` and `sampled_skus`, already stubbed on both adapters.
3. **Persist state.** `results` and `reviews` live on the `Workflow` object; move them to the `requests` and `reviews` tables.
4. **Real time.** The PoC uses each request's received time as "now"; production uses the clock.
5. **Pricing source.** `NetSuiteERP.price` calls the RESTlet; keep `s2q/pricing.py` as the test oracle that the RESTlet must agree with.
