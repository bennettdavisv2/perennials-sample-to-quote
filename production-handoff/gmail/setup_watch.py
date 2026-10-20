"""Start (or renew) the Gmail watch on quotes@ so new mail is pushed to the integration service.
SKELETON / SPEC: not run. Handoff E1–E3.

Prerequisites (Google Cloud + Workspace admin):
  1. Pub/Sub topic `s2q-gmail`; grant `gmail-api-push@system.gserviceaccount.com` the Publisher role on it.
  2. Push subscription on that topic -> https://<api-gateway>/webhooks/gmail, with an OIDC token
     (service account + audience = that URL) so handlers.gmail_push can verify the caller.
  3. A service account with domain-wide delegation, scope https://www.googleapis.com/auth/gmail.modify,
     impersonating quotes@ (read new mail, add the "s2q/processed" label).

A watch expires after 7 days: run this daily (EventBridge schedule in template.yaml) and store the
returned historyId / expiration in Postgres `gmail_state`.
"""
from __future__ import annotations

MAILBOX = "quotes@perennials.example"          # TODO: the real shared inbox
TOPIC = "projects/<gcp-project>/topics/s2q-gmail"


def start_watch():
    """gmail.users().watch(userId=MAILBOX, body={"topicName": TOPIC, "labelIds": ["INBOX"],
                                                  "labelFilterBehavior": "INCLUDE"}).execute()
    -> {"historyId": ..., "expiration": ms since epoch}; upsert into gmail_state."""
    raise NotImplementedError("google-api-python-client: build('gmail', 'v1', credentials=delegated_creds)")


if __name__ == "__main__":
    start_watch()
