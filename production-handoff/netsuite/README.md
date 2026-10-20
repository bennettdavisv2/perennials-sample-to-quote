# NetSuite building blocks

**Roadmap steps:** 1.5, 1.6, 4.2, 5.1–5.3 ([ROADMAP.md](../ROADMAP.md)).

**Skeleton / spec.** SuiteScript 2.1 files plus a record definition. Nothing here has been deployed to an account. Handoff items N1–N10 are in [`../REFERENCE.md`](../REFERENCE.md) §4.

| File | What it is | Handoff |
|---|---|---|
| `s2q_price_restlet.js` | Pricing RESTlet: trade + additive volume tier + cut fee, ported from `s2q/pricing.py`, with the test vectors it must match | N5 |
| `s2q_hold_expiry_mr.js` | Daily Map/Reduce that releases holds past `custbody_s2q_hold_expires` | N9 |

## Custom record: `customrecord_s2q_pricing_rule` (N4)
One active record. Merchandising edits it; the RESTlet reads it.

| Field id | Type | Example |
|---|---|---|
| `custrecord_s2q_trade_discount` | Percent | 15% |
| `custrecord_s2q_nontrade_discount` | Percent | 0% |
| `custrecord_s2q_volume_tiers` | Long text (JSON) | `[[100, 0.10], [50, 0.05]]` (min yards, extra discount; trade only, additive) |
| `custrecord_s2q_cut_fee` | Currency | $25 |
| `custrecord_s2q_cut_fee_under_yd` | Decimal | 5 |
| `custrecord_s2q_max_samples` | Integer | 10 |
| `custrecord_s2q_quote_valid_days` | Integer | 30 |
| `custrecord_s2q_hold_days` | Integer | 14 |

## Also needed (configuration, no code)
- **Items (N1–N2):** lot-numbered inventory items, one lot per dye lot; `custitem_s2q_lifecycle` (Active / Discontinued / Backorder) and `custitem_s2q_backorder_eta`.
- **Transaction body fields (N7):** `custbody_s2q_type` (list: Sample / Hold / CFA), `custbody_s2q_sf_quote_id`, `custbody_s2q_request_id`, `custbody_s2q_hold_expires`.
- **Forms (N7–N8):** S2Q Sample ($0), S2Q CFA ($0, lot-specific), and the hold, decided in N8.
- **Integration (N10):** an integration record with OAuth 2.0 client credentials, and a role limited to: customer create/edit, sales order create/edit/close, SuiteQL, RESTlet execute, item view.
