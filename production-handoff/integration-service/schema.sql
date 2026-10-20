-- Integration service state (RDS Postgres). SKELETON / SPEC: not applied to a database yet. Handoff §5.3.

-- One row per inbound request. source_id is the idempotency key: a webhook or Pub/Sub message
-- delivered twice inserts once (INSERT ... ON CONFLICT (source_id) DO NOTHING).
CREATE TABLE requests (
    id              text PRIMARY KEY,                 -- e.g. WEB-48213-S, EML-<gmail id>
    source          text NOT NULL CHECK (source IN ('woocommerce', 'gmail')),
    source_id       text NOT NULL UNIQUE,             -- woo:<order>:S|Q, gmail:<message id>
    customer_email  text NOT NULL,
    payload         jsonb NOT NULL,                   -- the s2q request dict
    extraction      jsonb,                            -- what CartIntake / Claude / rules read
    outcome         text,
    status          text NOT NULL DEFAULT 'queued',   -- queued | done | review | failed
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Every external call (the PoC's AuditLog): what was called, with what result.
CREATE TABLE audit_log (
    id              bigserial PRIMARY KEY,
    request_id      text REFERENCES requests(id),
    system          text NOT NULL,                    -- Salesforce | NetSuite | Claude | Gmail
    action          text NOT NULL,                    -- e.g. Create lead, Reserve inventory
    external_id     text,                             -- record id returned by the system
    status          text NOT NULL,                    -- ok | error
    error           text,
    model           text,                             -- Claude model id + prompt version, for extraction calls
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON audit_log (request_id);

-- Review items (mirrored as Salesforce Tasks / Quote approvals).
CREATE TABLE reviews (
    id              text PRIMARY KEY,                 -- REV-...
    request_id      text NOT NULL REFERENCES requests(id),
    sf_record_id    text UNIQUE,                      -- Task or Quote Id the callback refers to
    stage           text NOT NULL,
    reason          text NOT NULL,
    action          text NOT NULL,                    -- qualify_and_sample | place_samples_capped | send_quote | send_question
    payload         jsonb NOT NULL DEFAULT '{}',
    message         jsonb,                            -- drafted customer email {subject, body}
    asked           boolean NOT NULL DEFAULT false,
    status          text NOT NULL DEFAULT 'Open',
    decided_by      text,
    decided_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON reviews (status, created_at);         -- review-queue age alarm

-- Gmail watch state for quotes@perennialsfabrics.com.
CREATE TABLE gmail_state (
    mailbox          text PRIMARY KEY,                -- quotes@perennialsfabrics.com
    history_id       bigint NOT NULL,
    watch_expires_at timestamptz NOT NULL
);
