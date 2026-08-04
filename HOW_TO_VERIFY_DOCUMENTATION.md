# How to Verify Documentation

Use this checklist after doc changes or when onboarding a new developer.

---

## 1. Files exist (30 seconds)

```bash
ls README.md API.md ARCHITECTURE.md ONBOARDING.md VERIFICATION.md DOCS_UPDATE_SUMMARY.md
ls backend/scripts/verify_setup.py
```

---

## 2. Content spot-checks (2 minutes)

```bash
# All four domains
grep -c "Budget\|Mutual Funds\|Equity\|Tax Expert" README.md ARCHITECTURE.md

# Migrations 0001–0009
grep -c "0008\|0009\|access_requests\|users.status" ARCHITECTURE.md ONBOARDING.md

# Auth / admin-gated access (API catalog lives only in API.md)
grep -c "Bearer\|/auth/users\|access-status" API.md
grep -c "access control\|Admin Console" ARCHITECTURE.md ONBOARDING.md

# Environment variables
grep -c "FINANCEBUDDY_ADMIN_EMAILS\|SUPABASE_SERVICE_ROLE_KEY" ONBOARDING.md
```

Non-zero counts on each line indicate the major topics are still present.

---

## 3. Automated setup verification (5 minutes)

```bash
cd backend
python scripts/verify_setup.py
python -m migrations.migrate --status   # expect 0001–0009 applied
```

---

## 4. Auth documentation checklist

- [ ] ONBOARDING.md explains Supabase public sign-up lockdown (invite-only; no admin password set)
- [ ] ONBOARDING.md explains when `users` rows are created (first sign-in, not approval)
- [ ] **API.md** is the only full `/auth` endpoint table (includes DELETE routes + Bearer examples)
- [ ] API.md documents public rate limits (20/min IP+email) and logout await order
- [ ] ARCHITECTURE.md documents auth model + middleware + AdminOnly; links to API.md
- [ ] ONBOARDING lists production CORS warning (JWKS-only auth; no JWT secret)
- [ ] VERIFICATION.md includes auth/admin pre-deploy checks + `/auth/me` curl
- [ ] `tests/test_user_status_role.py` mentioned for DB-backed auth tests

---

## 5. Document map

| Document | Purpose |
|---|---|
| README.md | Overview, quick start, links |
| ONBOARDING.md | Setup — Supabase, OAuth, env, deploy |
| **API.md** | Call APIs, Bearer token, full `/auth` catalog |
| ARCHITECTURE.md | Design, domains, auth model, security |
| VERIFICATION.md | Post-setup validation checklist |
| DOCS_UPDATE_SUMMARY.md | Changelog of doc updates |

Cross-links: README → ONBOARDING, API, ARCHITECTURE, VERIFICATION.

---

## 6. Test commands

```bash
cd backend
python -m pytest tests/test_sql_is_valid_postgres.py -v
python -m pytest tests/test_only_shared_db_opens_connections.py -v

export TEST_DATABASE_URL=postgresql://postgres:pwd@localhost:5432/financebuddy_test
python -m pytest tests/test_user_status_role.py -v
python -m pytest tests/ -q   # ~875 tests with DB
```

---

## 7. New developer path (~1 hour)

1. **README.md** (5 min) — what the product does
2. **ONBOARDING.md** (40 min) — Supabase, env, run locally
3. **verify_setup.py** (2 min) — confirm config
4. **API.md** (10 min) — Bearer token + `/auth` routes
5. **ARCHITECTURE.md** (15 min) — domains + auth model
6. **VERIFICATION.md** (5 min) — pre-deploy checklist

---

Last updated: 2026-08-04
