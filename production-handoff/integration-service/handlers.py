"""Inbound endpoints (API Gateway -> Lambda). SKELETON / SPEC: not deployed or tested.

Each handler authenticates the caller, turns the event into one or more s2q requests (the same
dict shape the workbook rows use), and puts them on the SQS FIFO queue. No business logic here:
the worker runs s2q.workflow. Respond fast (WooCommerce and Pub/Sub retry on slow or non-2xx).

Handoff §5.1. Secrets from AWS Secrets Manager (names in template.yaml).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json


# --------------------------------------------------------------------------- shared
def enqueue(request: dict, idempotency_key: str) -> None:
    """Put one s2q request on the FIFO queue.

    - MessageGroupId = customer email: one customer's requests run in order (a revision must see
      the hold from the earlier quote), different customers run in parallel.
    - MessageDeduplicationId = idempotency_key; also inserted into Postgres `requests.source_id`
      (unique) by the worker, so a webhook delivered twice is processed once.
    """
    raise NotImplementedError("boto3 sqs.send_message(QueueUrl, MessageBody=json, MessageGroupId, MessageDeduplicationId)")


# --------------------------------------------------------------------------- WooCommerce (W3)
def verify_woocommerce_signature(raw_body: bytes, header_signature: str, secret: str) -> bool:
    """X-WC-Webhook-Signature = base64(HMAC-SHA256(secret, raw body)). Compare in constant time."""
    expected = base64.b64encode(hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected, header_signature or "")


def woocommerce_webhook(event: dict) -> dict:
    """POST /webhooks/woocommerce  (topic: order.created)

    1. verify_woocommerce_signature(event body, X-WC-Webhook-Signature) else 401.
    2. Ignore WooCommerce's ping on webhook creation (body has `webhook_id` only) -> 200.
    3. Split line_items by meta `_s2q_line_type` into sample lines and quote lines
       (same split as demo/site.py submit_checkout); build up to two requests:
         {"id": "WEB-<order id>[-S|-Q]", "type": "Sample request" | "Quote request", "channel": "Website form",
          "received": order date_created_gmt, "name", "company", "email" (billing),
          "message": customer_note,
          "cart": {"skus": [...]} or {"quote_lines": [{sku, length, unit, date_needed, cfa}]},
                  plus project_type, project_name, note}
    4. enqueue(each, idempotency_key=f"woo:{order_id}:{S|Q}") -> 200.
    """
    raise NotImplementedError


# --------------------------------------------------------------------------- Gmail push (E2/E3)
def gmail_push(event: dict) -> dict:
    """POST /webhooks/gmail  (Pub/Sub push subscription on topic s2q-gmail)

    1. Verify the Pub/Sub OIDC bearer token (audience = this endpoint) else 401.
    2. Decode message.data (base64 JSON: {"emailAddress", "historyId"}).
    3. Gmail API users.history.list(startHistoryId = gmail_state.history_id, historyTypes=["messageAdded"],
       labelId="INBOX") -> new message ids; update gmail_state.history_id.
    4. For each new message: users.messages.get(format="full"); skip our own replies and auto-replies;
       build {"id": "EML-<gmail id>", "type": "Quote request", "channel": "Email", "received", "name",
              "company": "", "email" (From), "message": plain-text body with quoted history stripped}
       enqueue(..., idempotency_key=f"gmail:{message_id}"); label the message "s2q/processed".
    5. Always 200 once parsed (Pub/Sub redelivers on error; idempotency makes that safe).
    """
    raise NotImplementedError


# --------------------------------------------------------------------------- Salesforce callback (S6)
def salesforce_callback(event: dict) -> dict:
    """POST /callbacks/salesforce  (from the record-triggered Flow's HTTP Callout, via Named Credential)

    Body: {"record_id": "<Task or Quote Id>", "decision": "approve" | "reject" | "ask", "user": "<username>"}
    1. Authenticate (shared secret header from the External Credential, or a signed JWT) else 401.
    2. Look up the review by sf_record_id in Postgres `reviews`.
    3. Enqueue {"kind": "decision", "review_id", "decision", "user"} with group = that customer's email,
       so the decision runs in order with the customer's other requests. The worker calls
       Workflow.approve / reject / ask (s2q/workflow.py).
    """
    raise NotImplementedError


def lambda_handler(event: dict, context) -> dict:
    """API Gateway router (template.yaml maps the three routes here)."""
    routes = {"/webhooks/woocommerce": woocommerce_webhook, "/webhooks/gmail": gmail_push,
              "/callbacks/salesforce": salesforce_callback}
    handler = routes.get(event.get("rawPath") or event.get("path"))
    if not handler:
        return {"statusCode": 404, "body": json.dumps({"error": "not found"})}
    return handler(event)
