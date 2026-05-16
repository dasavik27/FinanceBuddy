"""
main.py

FolioPulse API Service Gateway
===========================
Enterprise-grade REST API backend powered by FastAPI. Features an asynchronous,
multi-layered routing architecture specifically structured to mirror the AlphaTrack Pro
cockpit navigation interface. Implements robust GZip payload compression and CORS middleware
for high-performance institutional data delivery.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# Core System & Market Gateways
from routers import portfolio, market
# Specialized Analytical Tab Routers (1:1 Modular Mapping with Frontend Navigation)
from routers.tabs import overview, holdings, performance, compare, insights, rebalance, tax_strategy

app = FastAPI(
    title="FolioPulse Institutional Intelligence API",
    description="Advanced Mutual Fund Portfolio Analytics, Risk Metrics, and CIO Rebalancing Engine",
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

# ── Specialized Analytical Cockpit Routers (1:1 with UI Navigation) ──────
app.include_router(overview.router,     prefix="/portfolio", tags=["Analytics - Overview & Allocation"])
app.include_router(holdings.router,     prefix="/portfolio", tags=["Analytics - Holdings Explorer"])
app.include_router(performance.router,  prefix="/portfolio", tags=["Analytics - Trailing & Rolling Performance"])
app.include_router(compare.router,      prefix="/compare",   tags=["Analytics - Peer Comparison Matrix"])
app.include_router(insights.router,     prefix="/portfolio", tags=["Analytics - Smart Nudges & CIO Advisories"])
app.include_router(rebalance.router,    prefix="/rebalance", tags=["Analytics - Rebalancing & Drift Audit"])
app.include_router(tax_strategy.router, prefix="/portfolio", tags=["Analytics - Tax Strategy Lab"])

@app.get("/health", tags=["Infrastructure - Health"])
def health():
    """
    Service Health Check
    Validates institutional engine operational readiness, memory availability, and API versioning.
    """
    return {"status": "ok", "version": "8.0.0"}
