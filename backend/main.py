"""
FolioIQ · FastAPI Backend
Zero data retention · In-memory processing only
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import portfolio, benchmark, sip

app = FastAPI(
    title="FolioIQ API",
    description="Mutual Fund Portfolio Intelligence — Zero Data Retention",
    version="6.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
app.include_router(benchmark.router, prefix="/benchmark", tags=["benchmark"])
app.include_router(sip.router,       prefix="/sip",       tags=["sip"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "6.0.0"}
