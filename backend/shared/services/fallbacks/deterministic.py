import random
from typing import Dict
from services.fallbacks.base import InsightFallbackStrategy

class DeterministicFallback(InsightFallbackStrategy):
    """
    Implements a robust deterministic heuristic fallback engine.
    Uses seeded randomization based on the fund name and ISIN to guarantee that
    the same fund will always return the exact same fallback values, preserving UI consistency.
    """
    
    def generate_fallbacks(self, isin: str, category: str, fund_name: str, current_result: Dict) -> Dict:
        # Seed the random generator to guarantee deterministic outputs for the same fund
        seed = sum(ord(c) for c in fund_name + isin)
        rng = random.Random(seed)
        
        cat_u = category.upper()
        is_debt = any(k in cat_u for k in ["DEBT", "LIQUID", "GILT", "BOND"])
        
        if not current_result.get("aum"):
            base = 500 if is_debt else 1500
            current_result["aum"] = f"₹{rng.randint(base, base + 25000):,} Cr"
            current_result["aum_fallback"] = True
            
        if not current_result.get("risk"):
            current_result["risk_fallback"] = True
            if is_debt:
                current_result["risk"] = rng.choice(["LOW", "MODERATE"])
            elif "SMALL" in cat_u:
                current_result["risk"] = "VERY HIGH"
            else:
                current_result["risk"] = rng.choice(["HIGH", "MODERATELY HIGH"])
                
        if not current_result.get("exit_load"):
            current_result["exit_load_fallback"] = True
            if is_debt:
                current_result["exit_load"] = "Nil" if "LIQUID" in cat_u else "1% before 30 Days"
            else:
                current_result["exit_load"] = "1% before 1 Year"
                
        if not current_result.get("expense_ratio"):
            current_result["expense_ratio_fallback"] = True
            base_er = round(rng.uniform(0.15, 0.35) if is_debt else rng.uniform(0.35, 0.65), 2)
            
            # Apply ~0.80% industry-standard penalty markup if the fund is a Regular Plan
            if any(x in fund_name.upper() for x in ["REGULAR", "REG ", " REG"]):
                markup = round(rng.uniform(0.70, 0.90), 2)
                current_result["expense_ratio"] = round(base_er + markup, 2)
            else:
                current_result["expense_ratio"] = base_er
                
        return current_result
