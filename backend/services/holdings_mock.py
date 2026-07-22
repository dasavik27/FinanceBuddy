"""
services/holdings_mock.py

Synthetic Overlap Analysis Engine
Generates realistic stock holdings for mutual funds based on their category/cap type.
Used to detect portfolio concentration risk.
"""

import random

# Synthetic top 10 stocks by market cap category
MOCK_UNIVERSE = {
    "Large Cap": [
        ("HDFC Bank Ltd.", "Financials"),
        ("Reliance Industries Ltd.", "Energy"),
        ("ICICI Bank Ltd.", "Financials"),
        ("Infosys Ltd.", "IT"),
        ("Larsen & Toubro Ltd.", "Industrials"),
        ("TCS Ltd.", "IT"),
        ("ITC Ltd.", "Consumer Staples"),
        ("Bharti Airtel Ltd.", "Communication"),
        ("State Bank of India", "Financials"),
        ("Axis Bank Ltd.", "Financials"),
        ("Kotak Mahindra Bank Ltd.", "Financials"),
        ("Hindustan Unilever Ltd.", "Consumer Staples"),
    ],
    "Mid Cap": [
        ("Power Finance Corp", "Financials"),
        ("REC Ltd.", "Financials"),
        ("Trent Ltd.", "Consumer Discretionary"),
        ("TVS Motor Co Ltd.", "Automobiles"),
        ("Cummins India Ltd.", "Industrials"),
        ("Federal Bank Ltd.", "Financials"),
        ("Ashok Leyland Ltd.", "Automobiles"),
        ("Coforge Ltd.", "IT"),
        ("Voltas Ltd.", "Consumer Discretionary"),
        ("Polycab India Ltd.", "Industrials"),
    ],
    "Small Cap": [
        ("Suzlon Energy Ltd.", "Industrials"),
        ("BSE Ltd.", "Financials"),
        ("Cyient Ltd.", "IT"),
        ("KEI Industries Ltd.", "Industrials"),
        ("Sonata Software Ltd.", "IT"),
        ("Angel One Ltd.", "Financials"),
        ("Kalyan Jewellers India", "Consumer Discretionary"),
        ("Apar Industries Ltd.", "Industrials"),
        ("MCX India Ltd.", "Financials"),
        ("Karur Vysya Bank", "Financials"),
    ]
}

def _get_category_mix(cap_type: str, category: str):
    cap_type = cap_type.upper()
    cat = category.upper()
    
    if "SMALL" in cap_type:
        return {"Small Cap": 0.65, "Mid Cap": 0.25, "Large Cap": 0.10}
    elif "MID" in cap_type and "LARGE" not in cap_type:
        return {"Mid Cap": 0.65, "Small Cap": 0.20, "Large Cap": 0.15}
    elif "FLEXI" in cap_type or "MULTI" in cap_type or "ELSS" in cat:
        return {"Large Cap": 0.50, "Mid Cap": 0.30, "Small Cap": 0.20}
    elif "LARGE & MID" in cap_type:
        return {"Large Cap": 0.50, "Mid Cap": 0.40, "Small Cap": 0.10}
    else: # Default to Large Cap
        return {"Large Cap": 0.80, "Mid Cap": 0.15, "Small Cap": 0.05}

def get_mock_holdings(fund_name: str, category: str, cap_type: str) -> dict:
    """
    Returns a deterministic but seemingly random set of stock holdings
    for a given fund to simulate portfolio overlap.
    """
    # Use fund name hash as seed for deterministic results
    seed = sum(ord(c) for c in fund_name)
    rng = random.Random(seed)
    
    # Not applicable for debt/liquid
    if any(k in category.upper() for k in ["DEBT", "LIQUID", "COMMODIT", "INTERNATIONAL", "GLOBAL"]):
        return {}
        
    mix = _get_category_mix(cap_type, category)
    
    holdings = {}
    total_weight_assigned = 0.0
    
    # Assign top 15-20 stocks
    num_stocks = rng.randint(15, 25)
    
    for _ in range(num_stocks):
        # Pick cap category based on mix
        r = rng.random()
        cumulative = 0
        selected_cap = "Large Cap"
        for cap, weight in mix.items():
            cumulative += weight
            if r <= cumulative:
                selected_cap = cap
                break
                
        # Pick a stock from that cap
        universe = MOCK_UNIVERSE[selected_cap]
        stock_name, sector = rng.choice(universe)
        
        if stock_name not in holdings:
            # Assign a random weight between 1% and 6%
            w = rng.uniform(1.0, 6.0)
            holdings[stock_name] = {
                "sector": sector,
                "weight": w,
                "cap_type": selected_cap
            }
            total_weight_assigned += w
            
    # Normalize weights so the top 15-20 stocks make up about 40-60% of the fund
    target_top_weight = rng.uniform(40.0, 60.0)
    scale = target_top_weight / total_weight_assigned if total_weight_assigned > 0 else 1.0
    
    for k in holdings:
        holdings[k]["weight"] = round(holdings[k]["weight"] * scale, 2)
        
    return holdings
