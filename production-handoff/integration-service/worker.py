"""SQS FIFO consumer (Lambda). SKELETON / SPEC: not deployed or tested.

Runs the same workflow as the demo, s2q.workflow.Workflow, with real adapters and Postgres-backed
state instead of in-memory mocks. REFERENCE.md §5.2–5.4.
"""
from __future__ import annotations


def handle_record(message: dict) -> None:
    """One queue message: either an inbound request or a rep decision.

    Inbound request:
      1. INSERT INTO requests (source, source_id, ...) ON CONFLICT (source_id) DO NOTHING;
         if nothing was inserted it's a duplicate delivery -> return.
      2. wf = Workflow(crm=SalesforceCRM(...), erp=NetSuiteERP(...), store=PostgresStore(...), extractor=...)
         (today Workflow builds MockCRM / MockERP itself: make them constructor arguments, see README §Refactors)
      3. wf.process(request)  -> every external call is written to audit_log by the adapters.
      4. Update requests.status; review items are stored in `reviews` with the Salesforce Task / Quote Id.

    Decision ({"kind": "decision", ...}):
      wf.approve / wf.reject / wf.ask(review_id, by=user)

    Errors: let them raise. SQS retries (maxReceiveCount 3), then the message goes to the dead-letter
    queue, which raises a CloudWatch alarm. Claude API failures don't raise: the extractor falls back
    to rules and the request is flagged (s2q/extract.py).
    """
    raise NotImplementedError


def lambda_handler(event: dict, context) -> dict:
    """Batch from SQS. Report partial failures so only failed messages are retried
    (FunctionResponseTypes: ReportBatchItemFailures in template.yaml)."""
    records = event.get("Records", [])
    for i, record in enumerate(records):
        try:
            handle_record(record)
        except Exception:  # noqa: BLE001 - reported back to SQS for retry
            # FIFO: report this message AND every later one as failed, so nothing overtakes it.
            return {"batchItemFailures": [{"itemIdentifier": r["messageId"]} for r in records[i:]]}
    return {"batchItemFailures": []}
