-- 0006_budget_hardening: bring the budget tables up to the conventions the rest of
-- the schema already follows.
--
-- 0004 and 0005 introduced budget_payloads and budget_rules. Both are already applied
-- and checksummed, so migrate.py will not let them be edited (see the drift check at
-- migrations/migrate.py:122) - the corrections have to land as a new migration.
--
-- Three things were missing.
--
-- 1. Row-level security. 0002 enables RLS on every table holding user data and
--    explains why: it is a floor, so that an exposed anon key or a misconfigured
--    pooler yields an empty result set rather than everyone's data. budget_payloads
--    holds every transaction on the user's bank accounts and was the only user-data
--    table in the schema without it.
--
-- 2. A foreign key on budget_rules.user_id. Every other owner column in the schema is
--    `uuid REFERENCES users(id) ON DELETE CASCADE` (0001:42, 0001:51, 0001:69), and
--    shared/storage.py delete_all_for_user deletes only the users row and relies
--    entirely on those cascades. Without the FK, a full account purge left the user's
--    categorization rules - patterns they typed, often merchant names - in the table
--    forever, contradicting the guarantee that purge makes.
--
-- 3. Indexes for the queries the domain actually runs.
--
-- Note on 0005's `CREATE INDEX idx_budget_rules_user` (no IF NOT EXISTS): it is the
-- only unguarded CREATE INDEX in the tree. It cannot be fixed retroactively, because
-- editing 0005 changes its checksum. Any environment where that index already existed
-- before 0005 ran will have failed at 0005 and never reached this file; the fix there
-- is to drop the pre-existing index and re-run. Nothing to do here.

-- ── Row-level security ───────────────────────────────────────────────────────
--
-- ENABLE, not FORCE, matching 0002 exactly: the application connects as the table
-- owner and an owner bypasses RLS, so this is invisible to normal operation.

ALTER TABLE budget_payloads ENABLE ROW LEVEL SECURITY;
ALTER TABLE budget_rules    ENABLE ROW LEVEL SECURITY;

-- ── budget_rules.user_id: adopt the schema-wide ownership convention ─────────
--
-- Orphans first. A rule whose user_id names no account cannot be attributed to
-- anybody, cannot be reached through the API (every query filters on the caller's
-- user_id), and would block the constraint below. Deleting them is the same outcome
-- the cascade would have produced had it existed when the account was purged.

DELETE FROM budget_rules
WHERE user_id NOT IN (SELECT id FROM users);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_budget_rules_user'
    ) THEN
        ALTER TABLE budget_rules
            ADD CONSTRAINT fk_budget_rules_user
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;
END
$$;

-- ── Indexes ──────────────────────────────────────────────────────────────────

-- list_budget_sessions and get_all_budget_sessions both join budget_payloads to
-- sessions and filter on (user_id, upload_type). idx_sessions_owner_type (0001:92)
-- covers the sessions side; this covers the join back.
CREATE INDEX IF NOT EXISTS idx_budget_payloads_updated
    ON budget_payloads(updated_at DESC);

-- Rules are read in creation order for a single user on every upload.
CREATE INDEX IF NOT EXISTS idx_budget_rules_user_created
    ON budget_rules(user_id, created_at);

-- ── Constrain match_type to what the application can execute ─────────────────
--
-- rules_safety.MATCH_TYPES is the authority; this stops a value the matcher does not
-- understand from being stored by anything that bypasses the API (a fixture, a
-- console session) and then silently falling back to "contains" at match time.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_budget_rules_match_type'
    ) THEN
        ALTER TABLE budget_rules
            ADD CONSTRAINT ck_budget_rules_match_type
            CHECK (match_type IN ('contains', 'exact', 'starts_with', 'ends_with', 'regex'));
    END IF;
END
$$;
