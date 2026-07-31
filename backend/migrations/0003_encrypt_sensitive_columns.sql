-- 0003_encrypt_sensitive_columns: move PII into application-encrypted columns.
--
-- SECURITY.md recorded "data at rest is not encrypted" as the largest open item once
-- storage became durable. Volume encryption does not close it (the database decrypts
-- for anyone who authenticates) and neither does RLS from 0002 (this application
-- connects as the table owner, which bypasses it). Both leave a leaked connection
-- string or a stolen backup fully readable.
--
-- Encryption happens in the application (shared/crypto.py, AES-256-GCM), not in
-- pgcrypto: a pgcrypto key travels in the SQL statement, so it lands in
-- pg_stat_statements, in the server log on any error, and on the wire.
--
-- DESTRUCTIVE. Existing values in these columns are dropped rather than backfilled.
-- That is deliberate and safe here because no deployment has run these migrations
-- against real data yet. Were that not true, this would need a three-step
-- add-column / backfill-in-the-application / drop-column sequence instead - the
-- backfill cannot be done in SQL, because the database does not have the key.

-- ── profiles.pan ─────────────────────────────────────────────────────────────
-- The index goes with it. Encryption is randomised (fresh nonce per write), so
-- equal PANs produce different ciphertexts and a btree over them can serve no
-- lookup. Nothing queried by PAN anyway - it is read via user_id and used as the
-- CAS PDF password default.
DROP INDEX IF EXISTS idx_profiles_pan;
ALTER TABLE profiles DROP COLUMN IF EXISTS pan;
ALTER TABLE profiles ADD COLUMN pan_encrypted bytea;

-- ── sessions: the display metrics ────────────────────────────────────────────
-- total_value is the user's net worth and summary carries gross_salary, so leaving
-- them as plaintext doubles and jsonb would defeat the point of encrypting the
-- payloads. They collapse into one encrypted blob.
--
-- Safe to do because nothing filters, sorts or aggregates on them in SQL - the
-- history timeline fetches and displays them. Ordering is by created_at, which
-- stays plaintext.
ALTER TABLE sessions DROP COLUMN IF EXISTS total_value;
ALTER TABLE sessions DROP COLUMN IF EXISTS total_invested;
ALTER TABLE sessions DROP COLUMN IF EXISTS num_funds;
ALTER TABLE sessions DROP COLUMN IF EXISTS summary;
ALTER TABLE sessions ADD COLUMN metrics bytea;

-- ── tax_payloads.data ────────────────────────────────────────────────────────
-- The parsed AIS: salary, capital gains, deductions, PAN. jsonb -> bytea, because
-- ciphertext is not JSON and anything the database could index inside it would be
-- plaintext by definition. Nothing queried into this document; it is fetched whole.
ALTER TABLE tax_payloads DROP COLUMN IF EXISTS data;
ALTER TABLE tax_payloads ADD COLUMN data bytea;

-- session_payloads.holdings/transactions/sips are already bytea and keep their
-- type - the bytes are now ciphertext wrapping the compressed JSON rather than the
-- compressed JSON itself. No DDL needed.
--
-- Deliberately left in plaintext, with reasons:
--
--   sessions.data_hash      A SHA-256 over the ledger, salted with user_id. Dedup
--                           needs equality lookups, so it has to be deterministic;
--                           it is not reversible, and the user_id salt means it
--                           cannot be compared across accounts.
--   sessions.created_at     The history timeline orders by it.
--   sessions.upload_type    Used in every WHERE clause.
--   session_payloads.meta   Column names and datetime units. Schema, not data.
--   identities.email        Already known to the identity provider, and useful for
--                           support. Lower sensitivity than the financial columns.
--
-- statement_period stays too: a date range like "Apr 2023 - Mar 2024".
