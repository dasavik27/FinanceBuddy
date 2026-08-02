-- 0004_budget_module: schema for the new Budget Analyzer domain.

-- The new domain allows users to upload bank and credit card statements.
-- We store the encrypted parsed transactions here, linked to the `sessions` table.

CREATE TABLE IF NOT EXISTS budget_payloads (
    session_id   text PRIMARY KEY REFERENCES sessions(session_id) ON DELETE CASCADE,
    codec        text NOT NULL,
    transactions bytea,
    accounts     jsonb NOT NULL DEFAULT '{}'::jsonb,
    byte_size    integer,
    updated_at   timestamptz NOT NULL DEFAULT now()
);
