-- 0008_access_requests: Table to store invite-only early access requests.

CREATE TABLE IF NOT EXISTS access_requests (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         text NOT NULL,
    name          text NOT NULL,
    investor_type text NOT NULL DEFAULT 'individual',
    notes         text NOT NULL DEFAULT '',
    status        text NOT NULL DEFAULT 'pending',
    created_at    timestamptz NOT NULL DEFAULT now(),
    reviewed_at   timestamptz
);

CREATE INDEX IF NOT EXISTS idx_access_requests_email ON access_requests(email);
CREATE INDEX IF NOT EXISTS idx_access_requests_status ON access_requests(status, created_at DESC);
