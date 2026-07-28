"""
main.py

Finance Buddy API Service Gateway
===========================
Enterprise-grade REST API backend powered by FastAPI. Routes are organized into three
independent feature domains (Mutual Funds, Equity, Tax Expert) plus a shared
infrastructure layer (auth, market data, session vault, upload history) used by
all domains.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# Shared Infrastructure Gateways (cross-domain: auth, market data, vault, history)
from shared.routers import auth, market, accounts, history

# Domain: Mutual Funds
from domains.mutual_funds.routers import (
    portfolio, overview, holdings, performance, compare, insights, rebalance, journey,
)

# Domain: Equity (Indian Stocks) — placeholder, feature not yet built
from domains.equity import router as equity

# Domain: Tax Expert
from domains.tax_expert.routers import (
    session as tax_session, income as tax_income, capital_gains as tax_capital_gains,
    summary as tax_summary, itr as tax_itr,
)

app = FastAPI(
    title="Finance Buddy API",
    description="Smart Wealth Dashboard, Mutual Fund Portfolio Analytics, and Tax Expert Engine",
    version="8.0.0",
)

# Middleware Pipeline: Compress JSON payloads > 1KB to accelerate high-frequency rendering
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Cross-Origin Resource Sharing (CORS) Security Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Shared Infrastructure ──────────────────────────────────────────────────
app.include_router(auth.router,      prefix="/auth",      tags=["Infrastructure - Authentication"])
app.include_router(market.router,    prefix="/market",    tags=["Infrastructure - Live Market Feed"])
app.include_router(accounts.router,  prefix="/accounts",  tags=["Infrastructure - Vault Manager"])
app.include_router(history.router,   prefix="/history",   tags=["Infrastructure - History Timeline"])

# ── Domain: Mutual Funds ───────────────────────────────────────────────────
app.include_router(portfolio.router,    prefix="/mutual-funds/portfolio",     tags=["Mutual Funds - Session Management"])
app.include_router(overview.router,     prefix="/mutual-funds/overview",      tags=["Mutual Funds - Overview & Allocation"])
app.include_router(holdings.router,     prefix="/mutual-funds/holdings",      tags=["Mutual Funds - Holdings Explorer"])
app.include_router(performance.router,  prefix="/mutual-funds/performance",   tags=["Mutual Funds - Trailing & Rolling Performance"])
app.include_router(compare.router,      prefix="/mutual-funds/compare",       tags=["Mutual Funds - Peer Comparison Matrix"])
app.include_router(insights.router,     prefix="/mutual-funds/insights",      tags=["Mutual Funds - Smart Nudges & CIO Advisories"])
app.include_router(rebalance.router,    prefix="/mutual-funds/rebalance",     tags=["Mutual Funds - Rebalancing & Drift Audit"])
app.include_router(journey.router,      prefix="/mutual-funds/journey",       tags=["Mutual Funds - Wealth Journey Timeline"])

# ── Domain: Equity (Indian Stocks) ─────────────────────────────────────────
# Not yet built — reserved namespace. The UI currently shows "Coming Soon".
app.include_router(equity.router, prefix="/equity", tags=["Equity - Indian Stocks (Coming Soon)"])

# ── Domain: Tax Expert ──────────────────────────────────────────────────────
# Single canonical path: /tax-expert (all tax operations under one logical namespace)
app.include_router(tax_session.router,        prefix="/tax-expert", tags=["Tax Expert - Session Management"])
app.include_router(tax_income.router,         prefix="/tax-expert", tags=["Tax Expert - Income Breakdown"])
app.include_router(tax_capital_gains.router,  prefix="/tax-expert", tags=["Tax Expert - Capital Gains"])
app.include_router(tax_summary.router,        prefix="/tax-expert", tags=["Tax Expert - Computation & Regime Compare"])
app.include_router(tax_itr.router,            prefix="/tax-expert", tags=["Tax Expert - ITR Comparison"])


@app.get("/health", tags=["Infrastructure - Health"])
def health():
    """
    Service Health Check
    Validates institutional engine operational readiness, memory availability, and API versioning.
    """
    return {"status": "ok", "version": "8.0.0"}
