"""
core/broker_parser.py

Parses Broker Tax P&L files (e.g. Zerodha Excel) to extract structured
capital gains trade data for reconciliation against the government AIS.
"""

import io

def parse_zerodha_tax_pnl(raw_bytes: bytes) -> list:
    """
    Parses a Zerodha Tax P&L Excel file from raw bytes.
    Returns a flat list of trade dictionaries.
    """
    # Lazy import: broker reconciliation is optional, so pandas should not be a
    # cost of importing the tax domain. (It is still loaded eagerly by the
    # mutual-funds domain today; this keeps the tax path independent of that.)
    import pandas as pd

    xls = pd.ExcelFile(io.BytesIO(raw_bytes))
    trades = []
    
    # We target the summary sheets for easiest parsing
    target_sheets = ["Equity and Non Equity", "Mutual Funds"]
    
    for sheet in target_sheets:
        if sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            df = df.dropna(how='all')
            
            current_section = None
            current_slab = False

            for index, row in df.iterrows():
                row_vals = [str(x) for x in row.values if not pd.isna(x)]
                if not row_vals:
                    continue

                first_val = row_vals[0].strip()

                # Identify section headers
                if first_val.startswith("Short Term Trades") or first_val.startswith("Long Term Trades"):
                    current_section = "STCG" if "Short" in first_val else "LTCG"
                    current_slab = False
                    continue
                elif first_val.startswith("Debt") and "2023" in first_val:
                    # Units purchased on/after 2023-04-01 are always slab-taxed (Section 50AA).
                    current_section = "SLAB"
                    current_slab = True
                    continue
                elif first_val.startswith("Non Equity"):
                    current_section = None
                    current_slab = False
                    continue

                # Parse trade rows
                if current_section and len(row_vals) >= 5 and first_val != "Symbol":
                    try:
                        qty = float(row_vals[1].replace(',', ''))
                        buy = float(row_vals[2].replace(',', ''))
                        sell = float(row_vals[3].replace(',', ''))
                        pnl = float(row_vals[4].replace(',', ''))

                        trades.append({
                            "security": first_val,
                            "type": current_section,
                            "quantity": qty,
                            "cost": buy,
                            "consideration": sell,
                            "gain": pnl,
                            "slab_taxed": current_slab,
                            "source": "Zerodha"
                        })
                    except ValueError:
                        pass

    return trades
