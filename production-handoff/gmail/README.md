# Gmail (quotes@) building blocks

**Skeleton / spec.** Handoff items E1–E4 are in [`../README.md`](../README.md) §6.

- `setup_watch.py`: starts or renews the Gmail watch on quotes@. Run daily, because a watch expires after 7 days.
- The Pub/Sub push lands on `POST /webhooks/gmail` (`../integration-service/handlers.py`). That handler calls `users.history.list` from the stored historyId, fetches each new message and enqueues it.
- **Replies are sent from Salesforce** (org-wide quotes@ address, `emailSimple`), not from Gmail, so every customer email is logged on the Contact (S7).
