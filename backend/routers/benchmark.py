"""routers/benchmark.py — Benchmark data endpoints."""
from fastapi import APIRouter
from logic_adapter import BENCHMARKS, fetch_benchmark
import requests

router = APIRouter()


@router.get("/list")
def list_benchmarks():
    return {"benchmarks": list(BENCHMARKS.keys())}


@router.get("/search")
def search_ticker(q: str):
    """Yahoo Finance ticker search for the Compare tab."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&newsCount=0"
        resp = requests.get(url, headers=headers, timeout=5).json()
        quotes = resp.get("quotes", [])
        return {
            "results": [
                {
                    "symbol": qu["symbol"],
                    "name":   qu.get("longname", qu.get("shortname", "Unknown")),
                    "type":   qu.get("quoteType", ""),
                    "exchange": qu.get("exchange", ""),
                }
                for qu in quotes[:8]
            ]
        }
    except Exception:
        return {"results": []}


@router.get("/history")
def history(ticker: str, days: int = 365):
    """Return price history for any ticker (for the Compare chart)."""
    series = fetch_benchmark(ticker, days)
    if series.empty:
        return {"dates": [], "values": []}
    norm = series / series.iloc[0] * 100
    return {
        "dates":  series.index.strftime("%Y-%m-%d").tolist(),
        "values": norm.round(2).tolist(),
        "raw":    series.round(2).tolist(),
    }
