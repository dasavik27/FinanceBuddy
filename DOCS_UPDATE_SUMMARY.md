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

## Key Information

### Domains (All Documented)
- Budget Analyzer: /budget/* (3 routers)
- Mutual Funds: /mutual-funds/* (9 routers)
- Equity: /equity/* (6 routers)
- Tax Expert: /tax-expert/* (6 routers)

### Database Migrations
- 0001: Core schema
- 0002: Tax payloads
- 0003: Equity support
- 0004: Budget payloads (Aug 2, 2026)
- 0005: Budget rules (Aug 2, 2026)

### Session Caps (By Domain)
- Budget: 8 in-process sessions
- Mutual Funds: 3 in-process sessions
- Equity: 3 in-process sessions
- Tax Expert: 8 in-process sessions

---

## How to Use Documentation

1. **First setup:** Start with ONBOARDING.md
2. **Understand system:** Read ARCHITECTURE.md
3. **Budget details:** See BUDGET_ANALYSIS.md
4. **Verify setup:** Use VERIFICATION.md or run verify_setup.py
5. **Security questions:** Read SECURITY.md

---

## Quick Commands

```bash
# Run migrations
cd backend && python -m migrations.migrate

# Verify setup
python scripts/verify_setup.py

# Run tests
python -m pytest tests/test_sql_is_valid_postgres.py -v
python -m pytest tests/test_only_shared_db_opens_connections.py -v

# Run all tests
TEST_DATABASE_URL=postgresql://... python -m pytest tests/ -q
```

**All documentation updated: August 2, 2026**

---

# Update — August 3, 2026

Follows the domain-isolation and Budget refactor. Corrections outnumber additions
here: several things the previous pass recorded as documented were documented
*wrongly*, which is worse than a gap because it reads as verified.

## Corrections

| Document | Was | Now |
|---|---|---|
| BUDGET_ANALYSIS.md | API Reference documented `/api/budget/upload`, `/overview`, `/category_breakdown`, `/categorize` with invented response bodies | None of those paths ever existed. Replaced with all 26 real `/budget/*` routes, generated from the mounted app |
| BUDGET_ANALYSIS.md | Component table listed 7 components, called TransactionsTab "virtualized" | All 11 components; TransactionsTab is client-paginated at 50 rows, not virtualized |
| BUDGET_ANALYSIS.md | Cited `domains/budget/rules.py` | No such file — `categorizer.py` + `rules_safety.py` |
| ARCHITECTURE.md | Migrations 0002 "tax_payloads, indices", 0003 "equity support" | 0002 is row-level security, 0003 is column encryption. 0006 and 0007 were missing entirely |
| README.md | "362 tests" | 687 backend, 354 frontend |
| README.md, ONBOARDING.md | `npm run dev` at the repo root | There is no root package.json. `cd frontend && npm run dev:all` |
| VERIFICATION.md | "Expected: 362 tests pass" | 687, of which 111 skip without `TEST_DATABASE_URL` |
| ONBOARDING.md | 6 backend env vars | All 15 the code reads, split required/optional |
| HOW_TO_VERIFY_DOCUMENTATION.md | "All 5 migrations" | 7 |

## Additions

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
- Response-body examples are not reproduced in BUDGET_ANALYSIS.md. `GET /docs` is the
  source of truth — hand-copied payloads are what drifted last time.
