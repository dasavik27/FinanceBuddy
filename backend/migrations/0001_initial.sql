-- 0001_initial: the Postgres schema.
--
-- Replaces the SQLite database wholesale. Nothing is carried over: every session
-- on the old deployment lived on an ephemeral disk behind a 24h sweep, so there is
-- no data to migrate, and this is the one moment the partition key can change for
-- free.
--
-- The partition key is now `users.id`, not a PAN. PAN was simultaneously the login
-- credential, the owner column on every table, and the default CAS PDF password -
-- and it is a value printed on documents, so "anyone who knows a PAN can read that
-- user's data" was the actual security posture. It is demoted here to a profile
-- attribute.
--
-- Provider independence is deliberate. `users.id` is ours and is generated here, so
-- switching identity providers is an INSERT into `identities` rather than a re-key
-- of every table. Nothing references a provider-managed table such as Supabase's
-- auth.users - a foreign key to that is the single hardest thing to undo later.
-- Only gen_random_uuid() is assumed, which is core Postgres from 13 on, so this
-- schema applies unchanged to Supabase, Neon, RDS, Railway or a local server.

-- ── Identity ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz
);

-- (issuer, subject) is the provider's name for a person; user_id is ours.
-- Two rows can point at one user, which is what makes "sign in with Google, then
-- later also with Apple" work without duplicating the account.
CREATE TABLE IF NOT EXISTS identities (
    issuer     text NOT NULL,
    subject    text NOT NULL,
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email      text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (issuer, subject)
);

CREATE INDEX IF NOT EXISTS idx_identities_user ON identities(user_id);

CREATE TABLE IF NOT EXISTS profiles (
    user_id      uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    pan          text,
    display_name text,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- PAN is still looked up (AIS matching, the CAS password default) but is no longer
-- unique or required, because it no longer identifies anyone.
CREATE INDEX IF NOT EXISTS idx_profiles_pan ON profiles(pan) WHERE pan IS NOT NULL;

-- ── Sessions ─────────────────────────────────────────────────────────────────

-- One registry row per upload, for both domains. `upload_type` discriminates, which
-- is what lets GET /history serve mutual funds and tax expert through one query -
-- the frontend already sends X-Upload-Type. The tax store previously kept its own
-- table and could not appear in history at all.
CREATE TABLE IF NOT EXISTS sessions (
    session_id       text PRIMARY KEY,
    user_id          uuid REFERENCES users(id) ON DELETE CASCADE,
    upload_type      text NOT NULL DEFAULT 'mutual_funds',
    data_hash        text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    -- Denormalised so the history timeline renders without decompressing a payload.
    total_value      double precision,
    total_invested   double precision,
    num_funds        integer,
    is_partial       boolean NOT NULL DEFAULT false,
    statement_period text NOT NULL DEFAULT '',
    -- Small per-domain summary (tax: fy, gross_salary, total_tax, itr_type).
    summary          jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- Dedup is scoped to the owner: an identical ledger under two accounts must produce
-- two sessions. A plain UNIQUE(data_hash) let the second uploader be handed the
-- first uploader's session. Partial, because a NULL hash means "not deduplicable"
-- rather than "collides with every other NULL".
CREATE UNIQUE INDEX IF NOT EXISTS uq_sessions_hash_owner
    ON sessions(data_hash, user_id) WHERE data_hash IS NOT NULL;

-- Covers the filter and the sort for the history timeline and the accounts summary.
CREATE INDEX IF NOT EXISTS idx_sessions_owner_type
    ON sessions(user_id, upload_type, created_at DESC);

-- ── Payloads ─────────────────────────────────────────────────────────────────

-- The three mutual-fund frames, zlib-compressed. One row, one round trip, and no
-- schema to drift: the previous design created three tables implicitly from
-- DataFrame.to_sql and absorbed parser changes with runtime ALTER TABLE using
-- identifiers taken from the uploaded PDF. Postgres would not tolerate that, and
-- it should not have to.
--
-- Compressed in the application rather than left to TOAST, because TOAST
-- decompresses server-side before sending: doing it here saves the wire bytes too,
-- which is what matters once the database is a network hop away. Measured at 3.8x
-- on a 20k-row ledger (3.06 MB -> 0.81 MB).
CREATE TABLE IF NOT EXISTS session_payloads (
    session_id   text PRIMARY KEY REFERENCES sessions(session_id) ON DELETE CASCADE,
    codec        text NOT NULL,
    holdings     bytea,
    transactions bytea,
    sips         bytea,
    meta         jsonb NOT NULL DEFAULT '{}'::jsonb,
    byte_size    integer
);

-- The parsed AIS document. jsonb rather than bytea: it is far smaller than a CAS
-- ledger, and being queryable is worth more here than the compression would be.
CREATE TABLE IF NOT EXISTS tax_payloads (
    session_id text PRIMARY KEY REFERENCES sessions(session_id) ON DELETE CASCADE,
    data       jsonb NOT NULL,
    version    integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── Settings ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS app_settings (
    key   text PRIMARY KEY,
    value text NOT NULL
);
