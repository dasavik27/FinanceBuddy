"""
core/logic.py
Centralized categorization and intelligence logic.
"""

class CategorizationEngine:
    @staticmethod
    def detect_category(name: str, raw_cat: str = "", raw_type: str = "") -> str:
        # Priority 1: Use Raw Labels from CAS (Exact Data)
        rc = str(raw_cat or "").upper()
        rt = str(raw_type or "").upper()
        
        if "ELSS" in rc or "TAX SAVER" in rc: return "ELSS"
        if "LIQUID" in rc or "OVERNIGHT" in rc: return "Liquid"
        if "ARBITRAGE" in rc: return "Arbitrage"
        if "DIVIDEND" in rc: return "Dividend Yield"
        if "THEMATIC" in rc or "SECTORAL" in rc: return "Thematic"
        if "HYBRID" in rc or "BALANCED" in rc or "HYBRID" in rt or "BALANCED" in rt: return "Hybrid"
        if "DEBT" in rt or "DEBT" in rc or "BOND" in rc or "INCOME" in rc or "CREDIT RISK" in rc or "GILT" in rc or "LIQUID" in rc: return "Debt"
        if "INDEX" in rc or "ETF" in rc: return "Index"
        if "RETIREMENT" in rc or "CHILDREN" in rc: return "Solution Oriented"
        
        # Priority 2: Keyword Heuristics (Fallback)
        n = name.upper()
        if any(x in n for x in ["GOLD", "SILVER", "COMMODITY", "METAL", "COMMODITIES"]): return "Commodities"
        if any(x in n for x in ["NASDAQ", "S&P 500", "US ", "GLOBAL", "WORLD", "OVERSEAS", "INTERNATIONAL"]): return "International"
        if "ELSS" in n or "TAX SAVER" in n: return "ELSS"
        if "ARBITRAGE" in n: return "Arbitrage"
        if "LIQUID" in n or "OVERNIGHT" in n: return "Liquid"
        if any(x in n for x in ["HYBRID", "BALANCED", "EQUITY SAVINGS"]): return "Hybrid"
        if any(x in n for x in ["INDEX", "ETF"]): return "Index"

        # Priority 3: Comprehensive Debt Detection (Critical for tax classification)
        if "BANKING" in n and "PSU" in n: return "Debt"
        debt_keywords = [
            "DEBT", "BOND", "GILT", "MONEY MARKET", "FIXED", "DURATION",
            "INCOME FUND", "SAVINGS FUND", "ALL SEASONS", "CORPORATE BOND",
            "CREDIT RISK", "SHORT DURATION", "MEDIUM DURATION", "DYNAMIC BOND",
            "FLOATING RATE", "LOW DURATION", "ULTRA SHORT",
        ]
        if any(x in n for x in debt_keywords): return "Debt"
        if "BANKING" in n:
            return "Thematic"
            
        # Final Priority: Use Raw Category if available
        if raw_cat and len(raw_cat) > 3:
            return raw_cat.strip().title()
            
        return "Equity"

    @staticmethod
    def detect_cap_type(name: str, category: str, raw_cat: str = "") -> str:
        n = name.upper()
        rc = str(raw_cat or "").upper()
        
        if category in ["Debt", "Liquid", "Arbitrage"]:
            return "N/A"
        
        # Priority 1: Exact Style/Market Matching
        if "INTERNATIONAL" in rc or "INTERNATIONAL" in n or "GLOBAL" in n or "US " in n: return "International"
        if "THEMATIC" in rc or "SECTORAL" in rc or "INFRA" in n or "PHARMA" in n or "TECH" in n: return "Thematic"
        if "DIVIDEND" in rc or "DIVIDEND" in n: return "Dividend Yield"
        if "COMMODITY" in rc or "GOLD" in n or "SILVER" in n: return "Commodity"
        
        # Priority 2: Raw Category exact cap match
        if "SMALL" in rc: return "Small Cap"
        if "MID" in rc and "LARGE" in rc: return "Large & Mid Cap"
        if "MID" in rc: return "Mid Cap"
        if "FLEXI" in rc: return "Flexi Cap"
        if "MULTI" in rc: return "Multi Cap"
        if "LARGE" in rc: return "Large Cap"
        
        # Priority 3: Name Keyword matching
        if "LARGE" in n and "MID" in n: return "Large & Mid Cap"
        if "SMALL" in n: return "Small Cap"
        if "MID" in n:   return "Mid Cap"
        if "FLEXI" in n: return "Flexi Cap"
        if "MULTI" in n: return "Multi Cap"
        if "LARGE" in n: return "Large Cap"
        
        # Priority 4: Style-based Labels
        if "VALUE" in rc or "VALUE" in n: return "Value"
        if "CONTRA" in rc or "CONTRA" in n: return "Contra"
        if "FOCUSED" in rc or "FOCUSED" in n: return "Focused"
        
        # Fallbacks
        if category == "ELSS": return "Flexi Cap"
        if category == "Index":
            if "NIFTY 50" in n or "SENSEX" in n: return "Large Cap"
            if "MIDCAP" in n or "MID CAP" in n: return "Mid Cap"
            if "SMALLCAP" in n or "SMALL CAP" in n: return "Small Cap"
            if "NEXT 50" in n: return "Large Cap"
            return "Large Cap"
            
        return "Large Cap"

    @staticmethod
    def detect_amc(name: str, raw_amc: str = "") -> str:
        if raw_amc and len(raw_amc) > 2:
            return raw_amc.replace(" Mutual Fund", "").replace(" MF", "").strip()
            
        amcs = {
            "Mirae": "Mirae Asset", "HDFC": "HDFC", "SBI": "SBI", "Axis": "Axis", "ICICI": "ICICI Prudential",
            "Nippon": "Nippon India", "Bandhan": "Bandhan", "Kotak": "Kotak", "Aditya Birla": "Aditya Birla Sun Life",
            "Parag Parikh": "Parag Parikh", "Motilal": "Motilal Oswal", "Canara": "Canara Robeco", "Quant": "Quant"
        }
        n = name.upper()
        for k, v in amcs.items():
            if k.upper() in n:
                return v
        return "Other"

    @staticmethod
    def detect_plan(name: str) -> str:
        n = name.upper()
        if "DIRECT" in n: return "Direct"
        if "REGULAR" in n: return "Regular"
        return "Unknown"

    @staticmethod
    def extract_amc_brand(fund_name: str) -> str:
        """
        Extract the AMC brand name from a fund name for peer diversity filtering.
        Centralized to eliminate code duplication across tab routers (Fix M-12).
        """
        name = fund_name.upper().strip()
        for compound in [
            "NIPPON INDIA", "ICICI PRUDENTIAL", "ADITYA BIRLA", "MIRAE ASSET",
            "FRANKLIN TEMPLETON", "MOTILAL OSWAL", "CANARA ROBECO", "TATA", "DSP",
            "SBI", "HDFC", "QUANT", "AXIS", "KOTAK", "BANDHAN", "UTI", "PPFAS",
            "PARAG PARIKH", "SUNDARAM", "EDELWEISS", "INVESCO", "HSBC", "PGIM",
            "BARODA BNP", "MAHINDRA", "LIC", "BANK OF INDIA", "UNION", "JM",
            "ITI", "GROWW", "SAMCO", "ZERODHA", "360 ONE", "BAJAJ FINSERV",
            "WHITEOAK", "OLD BRIDGE", "HELIOS", "NJ",
        ]:
            if name.startswith(compound):
                return compound
        return name.split()[0] if name.split() else "UNKNOWN"
