-- 0002_rls_deny_all: row-level security as a backstop, not as the access control.
--
-- Authorization is enforced in the application, at the data-access boundary
-- (shared/identity.py owns_record, called from get_session / get_tax_session /
-- get_history). That is where it stays: it is tested, it produces the right HTTP
-- status codes, and it works the same against any Postgres.
--
-- What this adds is a floor. Enabling RLS with no permissive policy means a
-- connection that is *not* the owning role reads nothing at all - so if an anon or
-- publishable key is ever exposed, or a pooler is misconfigured, the failure mode is
-- an empty result set rather than a full table scan of everyone's holdings.
--
-- The application connects as the table owner, and an owner bypasses RLS by default,
-- so this is invisible to normal operation. FORCE would apply it to the owner too,
-- which would require per-request session variables that a transaction-mode pooler
-- makes awkward - deliberately not done. Revisit only if the frontend is ever given
-- direct database access, at which point policies keyed on the JWT subject become
-- worth the complexity.
--
-- Portable: RLS is core Postgres, not a vendor feature.

ALTER TABLE users            ENABLE ROW LEVEL SECURITY;
ALTER TABLE identities       ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles         ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions         ENABLE ROW LEVEL SECURITY;
ALTER TABLE session_payloads ENABLE ROW LEVEL SECURITY;
ALTER TABLE tax_payloads     ENABLE ROW LEVEL SECURITY;

-- app_settings is deliberately excluded: it holds one operator-set cache TTL, no
-- personal data, and is read during startup.
