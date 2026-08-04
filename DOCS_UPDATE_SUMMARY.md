# Documentation Update Summary

**Date:** August 2, 2026
**Updated By:** Claude Code

---

## Files Updated

### 1. README.md
✓ Updated with Budget domain, Verification section

### 2. ARCHITECTURE.md
✓ Added Budget domain, 4-domain description, URL table, sessions caps

### 3. ONBOARDING.md
✓ Added migrations table (0001-0005), Budget references, env var table

### 4. VERIFICATION.md
✓ Created - Complete setup validation checklist with scripts

### 5. backend/scripts/verify_setup.py
✓ Created - Python script for setup validation

---

## What Was Added

### Documentation
- Budget domain references throughout all docs
- New VERIFICATION.md with complete checklist
- Database migrations table (0001-0005)
- Budget-specific setup instructions
- Complete environment variable reference

### Scripts
- backend/scripts/verify_setup.py - Setup validation

---

## Key Information (current — supersedes Aug 2 bullets below)

Canonical sources: [ARCHITECTURE.md](ARCHITECTURE.md), [ONBOARDING.md](ONBOARDING.md), [API.md](API.md).

| Area | Fact |
|---|---|
| Domains | Budget **5** routers; MF 9; Equity 6; Tax 6 |
| Migrations | **0001–0009** (0002=RLS, 0003=encryption, 0008=access_requests, 0009=status/role) |
| Session caps | MF 3 / Equity 3 / Tax 8 (env); Budget has no resident-session env cap |
| Auth API catalog | **API.md** only (do not duplicate elsewhere) |
| Backend tests | ~**875** collected |

## How to Use Documentation

1. **First setup:** Start with ONBOARDING.md
2. **Call APIs / tokens:** API.md
3. **Understand system:** ARCHITECTURE.md
4. **Verify setup:** VERIFICATION.md or `cd backend && python scripts/verify_setup.py`

---

## Quick Commands

```bash
# Run migrations
cd backend && python -m migrations.migrate

# Verify setup
cd backend && python scripts/verify_setup.py

# Run tests
python -m pytest tests/test_sql_is_valid_postgres.py -v
python -m pytest tests/test_only_shared_db_opens_connections.py -v

# Run all tests
TEST_DATABASE_URL=postgresql://... python -m pytest tests/ -q
```

---

# Update — August 3, 2026

Follows the domain-isolation and Budget refactor. Corrections outnumber additions
here: several things the previous pass recorded as documented were documented
*wrongly*, which is worse than a gap because it reads as verified.

## Corrections

| Document | Was | Now |
|---|---|---|
| ARCHITECTURE.md | System overview only | Comprehensive technical architecture + full Budget Analyzer domain architecture, ingestion pipeline, computational engines, and component hierarchy (merged from BUDGET_ANALYSIS.md) |
| ARCHITECTURE.md | Migrations 0002 "tax_payloads, indices", 0003 "equity support" | 0002 is row-level security, 0003 is column encryption. 0006 and 0007 were missing entirely |
| README.md | "362 tests" | 687 backend, 354 frontend |
| README.md, ONBOARDING.md | `npm run dev` at the repo root | There is no root package.json. `cd frontend && npm run dev:all` |
| VERIFICATION.md | "Expected: 362 tests pass" | 687, of which 111 skip without `TEST_DATABASE_URL` |
| ONBOARDING.md | 6 backend env vars | All 15 the code reads, split required/optional |
| HOW_TO_VERIFY_DOCUMENTATION.md | "All 5 migrations" | 7 |

## Additions

- **ARCHITECTURE.md — Budget Analyzer domain architecture & engines.** Merged all technical details, bank ingestion parser specs, 50/30/20 scoring algorithm, dynamic filtering system, `/budget/*` API reference, and frontend components into [ARCHITECTURE.md](ARCHITECTURE.md).
- **ARCHITECTURE.md — Frontend routes.** Domains moved from `/dashboard/<domain>` to
  top-level `/<domain>`; `/dashboard` is now the hub. Legacy URLs redirect.
- **ARCHITECTURE.md — Keeping the domains independent.** The `janitor` and
  `session_stores` registries, and the three rules that keep cross-domain coupling at
  zero. This is the part most likely to be undone by accident.
- **ARCHITECTURE.md — Backend tree** now shows `shared/reference/`,
  `shared/services/returns.py`, `janitor.py`, `session_stores.py`.

## Known gaps, deliberately left

- `HOW_TO_VERIFY_DOCUMENTATION.md` asserts "ALL DOCUMENTATION COMPLETE ✓" and lists
  file sizes from August 2. A document that certifies its own completeness will keep
  going stale; worth deleting rather than maintaining.
- Response-body examples are not reproduced in ARCHITECTURE.md. `GET /docs` is the
  source of truth — hand-copied payloads are what drifted last time.

---

# Update — August 4, 2026

Admin-gated login, Admin Console user management, and documentation sync.

## Additions

| Document | What changed |
|---|---|
| **ARCHITECTURE.md** | New *Authentication & access control* section: two-layer auth, status/role, allowlist rules, middleware gates, frontend auth screens; migrations 0008–0009; `/admin` route |
| **API.md** | Canonical `/auth` catalog + how to pass Supabase `access_token` Bearer header; OpenAPI for schemas |
| **ONBOARDING.md** | Access flow; JWT secret + CORS prod warnings; Procfile release/`--workers 1`; full env catalog |
| **README.md** | Invite/approve-only sign-in; API.md link; ~875 backend tests |
| **VERIFICATION.md** | Auth/admin/CORS/JWT pre-deploy checklist; points at live `verify_setup.py` |
| **backend/scripts/verify_setup.py** | Tables + migrations; warns on JWT secret, CORS, admin emails, service role |

## Key concepts now documented

- **`access_requests`** (0008) — public form + admin allowlist; approval does **not** insert into `users`
- **`users.status` / `users.role`** (0009) — pending / active / suspended; user / admin
- **First sign-in** — `users.resolve()` creates the app account when email is allowlisted
- **Admin APIs** — list/update/delete users, suspend, invites, approve/reject (catalog in API.md)
- **Removed from product** — local dev one-click sign-in; `GET /auth/provisioning-status`; `FINANCEBUDDY_OPEN_PROVISION`
