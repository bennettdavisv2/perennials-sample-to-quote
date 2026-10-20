# WooCommerce → integration service

Handoff items W1 to W5. Owner: WooCommerce / WordPress developer.

## Setup (W3)
1. WooCommerce → Settings → Advanced → Webhooks → **Add webhook**.
2. Name `s2q-order-created`, status **Active**, topic **Order created**.
3. Delivery URL: `https://<api-gateway>/webhooks/woocommerce`.
4. Secret: generate one and store it in AWS Secrets Manager as `s2q/woocommerce-webhook-secret`.
5. API version: WP REST API Integration v3.

WooCommerce signs each delivery: header `X-WC-Webhook-Signature` = base64(HMAC-SHA256(secret, raw body)). The service rejects anything that doesn't match (see `../integration-service/handlers.py`).

## What the service reads from the order payload
Only the fields below. Everything else in the payload is ignored.

```jsonc
{
  "id": 48213,                                  // idempotency key: "woo:48213"
  "billing": {"first_name": "Dana", "last_name": "Ruiz", "company": "Ruiz Interiors",
              "email": "dana@ruizinteriors.example"},
  "customer_id": 0,                             // 0 = guest checkout (README assumption 19)
  "customer_note": "Sidemark: LOWE / Malibu",   // the order note (free text, read for who is asking)
  "line_items": [
    {"sku": "PF-1008", "meta_data": [           // sample line
      {"key": "_s2q_line_type", "value": "sample"},
      {"key": "_s2q_project_type", "value": "hospitality"}]},
    {"sku": "PF-1006", "meta_data": [           // quote line from "Request A Quote"
      {"key": "_s2q_line_type", "value": "quote"},
      {"key": "_s2q_length", "value": "90"}, {"key": "_s2q_length_unit", "value": "feet"},
      {"key": "_s2q_date_needed", "value": "2026-11-20"}, {"key": "_s2q_cfa", "value": "requested"},
      {"key": "_s2q_project_name", "value": "Beach house living room, Malibu"},
      {"key": "_s2q_project_type", "value": "residential"}]}
  ]
}
```

The service splits one order into up to two requests (sample lines and quote lines), exactly as `demo/site.py` does. Each becomes the `cart` shape that `s2q.extract.CartIntake` already reads.

## Checks before go-live
- **W1 SKU audit:** export every variation SKU and diff it against the NetSuite item list. Any mismatch is an order that can't be fulfilled automatically.
- **W5 discontinued items:** hide "Add Sample" for variations NetSuite marks discontinued, using an attribute synced nightly by the service.
- Place a test order on staging and confirm the meta keys above appear in the webhook payload, e.g. via the webhook's delivery log.
