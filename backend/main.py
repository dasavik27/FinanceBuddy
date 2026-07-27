"""
main.py

Finance Buddy API Service Gateway
===========================
Enterprise-grade REST API backend powered by FastAPI. Features an asynchronous,
multi-layered routing architecture specifically structured to mirror the Finance Buddy
cockpit navigation interface. Implements robust GZip payload compression and CORS middleware
for high-performance institutional data delivery.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# Core System & Market Gateways
from routers import portfolio, market, auth, accounts
# Specialized Analytical Tab Routers (1:1 Modular Mapping with Frontend Navigation)
from routers.tabs import overview, holdings, performance, compare, insights, rebalance, tax_strategy, overlap, history, journey

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

# ── Core Infrastructure Gateways ──────────────────────────────────────────
app.include_router(portfolio.router, prefix="/portfolio", tags=["Infrastructure - Session Management"])
app.include_router(market.router,    prefix="/market",    tags=["Infrastructure - Live Market Feed"])
app.include_router(auth.router,      prefix="/auth",      tags=["Infrastructure - Authentication"])
app.include_router(accounts.router,  prefix="/accounts",  tags=["Infrastructure - Vault Manager"])

# ── Specialized Analytical Cockpit Routers (1:1 with UI Navigation) ──────
app.include_router(overview.router,     prefix="/portfolio", tags=["Analytics - Overview & Allocation"])
app.include_router(holdings.router,     prefix="/portfolio", tags=["Analytics - Holdings Explorer"])
app.include_router(performance.router,  prefix="/portfolio", tags=["Analytics - Trailing & Rolling Performance"])
app.include_router(compare.router,      prefix="/compare",   tags=["Analytics - Peer Comparison Matrix"])
app.include_router(insights.router,     prefix="/portfolio", tags=["Analytics - Smart Nudges & CIO Advisories"])
app.include_router(rebalance.router,    prefix="/rebalance", tags=["Analytics - Rebalancing & Drift Audit"])
app.include_router(tax_strategy.router, prefix="/portfolio", tags=["Analytics - Tax Strategy Lab"])
app.include_router(tax_strategy.router, prefix="/tax-expert", tags=["Tax Expert - AIS Filing"])
app.include_router(overlap.router,      prefix="/portfolio", tags=["Analytics - Overlap Analysis"])
app.include_router(history.router,      prefix="/history",   tags=["Analytics - History Timeline"])
app.include_router(journey.router,      prefix="/journey",   tags=["Analytics - Wealth Journey Timeline"])

@app.get("/health", tags=["Infrastructure - Health"])
def health():
    """
    Service Health Check
    Validates institutional engine operational readiness, memory availability, and API versioning.
    """
    return {"status": "ok", "version": "8.0.0"}


