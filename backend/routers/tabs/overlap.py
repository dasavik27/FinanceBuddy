from fastapi import APIRouter
from core.sessions import get_session
from services.holdings_mock import get_mock_holdings

router = APIRouter()

@router.get("/{session_id}/overlap")
def get_portfolio_overlap(session_id: str):
    """
    Computes pairwise fund overlap and top concentrated stocks
    across the entire equity portfolio using synthetic holdings data.
    """
    portfolio = get_session(session_id)
    df_h = portfolio.df_h
    
    if df_h.empty:
        return {"pairs": [], "top_stocks": [], "overall_concentration_score": 0}

    # Filter out debt and liquid funds, get only active equity
    equity_funds = []
    fund_holdings = {}
    
    total_equity_value = 0
    
    for _, row in df_h.iterrows():
        cat = str(row.get("Category", "Equity")).upper()
        cap_type = str(row.get("Cap Type", ""))
        fn = str(row.get("Fund", ""))
        val = float(row.get("Market Value", 0))
        
        if val <= 0:
            continue
            
        if any(k in cat for k in ["DEBT", "LIQUID", "COMMODIT", "INTERNATIONAL"]):
            continue
            
        holdings = get_mock_holdings(fn, cat, cap_type)
        if not holdings:
            continue
            
        equity_funds.append({"name": fn, "value": val, "holdings": holdings})
        fund_holdings[fn] = holdings
        total_equity_value += val
        
    if len(equity_funds) < 2:
        return {"pairs": [], "top_stocks": [], "overall_concentration_score": 0}
        
    # Calculate pairwise overlap
    pairs = []
    for i in range(len(equity_funds)):
        for j in range(i + 1, len(equity_funds)):
            f1 = equity_funds[i]
            f2 = equity_funds[j]
            
            h1 = f1["holdings"]
            h2 = f2["holdings"]
            
            common_stocks = set(h1.keys()).intersection(set(h2.keys()))
                
            overlap_score = 0
            shared_assets = []
            
            for stock in common_stocks:
                # Minimum of the weights in both funds represents the true overlap
                w1 = h1[stock]["weight"]
                w2 = h2[stock]["weight"]
                w_min = min(w1, w2)
                overlap_score += w_min
                shared_assets.append({
                    "stock": stock,
                    "overlap_weight": w_min
                })
                
            pairs.append({
                "fund1": f1["name"],
                "fund2": f2["name"],
                "overlap_pct": round(overlap_score, 2),
                "shared_count": len(common_stocks),
                "shared_stocks": sorted(shared_assets, key=lambda x: x["overlap_weight"], reverse=True)[:5]
            })
                
    # Sort pairs by highest overlap
    pairs = sorted(pairs, key=lambda x: x["overlap_pct"], reverse=True)
    
    # Calculate overall portfolio stock concentration
    portfolio_stocks = {}
    
    for f in equity_funds:
        weight_in_portfolio = f["value"] / total_equity_value
        for stock, data in f["holdings"].items():
            contrib = data["weight"] * weight_in_portfolio
            if stock not in portfolio_stocks:
                portfolio_stocks[stock] = {
                    "sector": data["sector"],
                    "cap_type": data["cap_type"],
                    "total_portfolio_weight": 0,
                    "held_by": []
                }
            portfolio_stocks[stock]["total_portfolio_weight"] += contrib
            portfolio_stocks[stock]["held_by"].append(f["name"])
            
    # Format top stocks
    top_stocks = []
    for stock, data in portfolio_stocks.items():
        if data["total_portfolio_weight"] > 1.0: # Only report if > 1% of equity portfolio
            top_stocks.append({
                "stock": stock,
                "sector": data["sector"],
                "cap_type": data["cap_type"],
                "portfolio_weight": round(data["total_portfolio_weight"], 2),
                "fund_count": len(data["held_by"])
            })
            
    top_stocks = sorted(top_stocks, key=lambda x: x["portfolio_weight"], reverse=True)[:10]
    
    # Concentration score: high if top 5 stocks make up > 25% of the portfolio
    top5_weight = sum(s["portfolio_weight"] for s in top_stocks[:5])
    concentration_score = min(100, (top5_weight / 30.0) * 100)
    
    return {
        "pairs": pairs,
        "top_stocks": top_stocks,
        "overall_concentration_score": round(concentration_score, 1),
        "equity_funds_analyzed": len(equity_funds)
    }
