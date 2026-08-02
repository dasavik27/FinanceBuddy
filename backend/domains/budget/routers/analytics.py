import logging
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from typing import List, Optional
from shared import identity
from domains.budget.sessions import get_budget_session, get_all_budget_sessions, update_budget_transactions
import datetime
import re

logger = logging.getLogger(__name__)

router = APIRouter(tags=["budget"])

def _clean_merchant_name(desc: str) -> str:
    if not desc or str(desc).strip().lower() in ("nan", "none", "null", ""):
        return "Uncategorized Payee"
    raw = str(desc).strip()
    # Remove common banking prefix noise
    clean = re.sub(r'^(UPI/(DR|CR)/[\d\w]+/|POS\s*\d*\s*|NEFT[-\s]*\d*[-\s]*|RTGS[-\s]*\d*[-\s]*|IMPS[-\s]*\d*[-\s]*|ACH\s*[DC][-\s]*|INF\*|BIL/|E-COMM\s*|INB\s*)', '', raw, flags=re.IGNORECASE).strip()
    clean = re.sub(r'[/@].*$', '', clean).strip()  # Cut off after / or @ (like @okaxis or /paytm)
    clean = re.sub(r'\s{2,}', ' ', clean)
    if clean.lower() in ("nan", "none", "null", ""):
        return "Uncategorized Payee"
    if len(clean) > 28:
        clean = clean[:25] + "..."
    return clean.title() if clean else raw[:25].title()

def _infer_payment_mode(desc: str) -> str:
    if not desc:
        return "other"
    d = str(desc).lower()
    if "upi" in d or "@" in d:
        return "upi"
    if any(k in d for k in ["pos", "e-comm", "card", "swipe", "visa", "mastercard"]):
        return "card"
    if any(k in d for k in ["neft", "rtgs", "imps", "inb", "transfer", "netbanking"]):
        return "netbanking"
    if any(k in d for k in ["atm", "cash wdl", "cash dep", "nfs"]):
        return "atm"
    if any(k in d for k in ["ach", "nach", "bil/", "mandate", "standing instruction", "si-"]):
        return "autodebit"
    return "other"

def _apply_budget_filters(
    df: pd.DataFrame,
    bank: Optional[str] = None,
    account_type: Optional[str] = None,
    txn_type: Optional[str] = None,
    date_range: Optional[str] = "all",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    amount_bracket: Optional[str] = "all",
    payment_mode: Optional[str] = "all",
    category: Optional[str] = "all",
    search: Optional[str] = None
) -> pd.DataFrame:
    if df.empty:
        return df

    # Bank filter
    if bank and bank.lower() != "all" and "source_bank" in df.columns:
        df = df[df["source_bank"].str.upper() == bank.upper()]

    # Account Type filter
    if account_type and account_type.lower() != "all" and "account_type" in df.columns:
        df = df[df["account_type"].str.lower() == account_type.lower()]

    # Transaction Type / Flow filter (Debit vs Credit)
    if txn_type and txn_type.lower() != "all" and "type" in df.columns:
        df = df[df["type"].str.lower() == txn_type.lower()]

    # Category filter
    if category and category.lower() != "all" and "category" in df.columns:
        df = df[df["category"].str.lower() == category.lower()]

    # Amount Bracket filter
    if amount_bracket and amount_bracket.lower() != "all" and "amount" in df.columns:
        amt = df["amount"]
        if amount_bracket == "micro":
            df = df[amt < 500]
        elif amount_bracket == "small":
            df = df[(amt >= 500) & (amt < 2000)]
        elif amount_bracket == "medium":
            df = df[(amt >= 2000) & (amt < 10000)]
        elif amount_bracket == "large":
            df = df[amt >= 10000]

    # Payment Mode filter
    if payment_mode and payment_mode.lower() != "all" and "description" in df.columns:
        modes = df["description"].apply(_infer_payment_mode)
        df = df[modes == payment_mode.lower()]

    # Search keyword filter
    if search and search.strip():
        q = search.strip().lower()
        search_mask = pd.Series(False, index=df.index)
        for col in ["description", "notes", "category", "source_bank"]:
            if col in df.columns:
                search_mask = search_mask | df[col].astype(str).str.lower().str.contains(q, na=False)
        df = df[search_mask]

    # Date Range filter
    if "date" in df.columns and not df.empty:
        df["parsed_date"] = pd.to_datetime(df["date"], errors="coerce")
        max_dt = df["parsed_date"].max()
        if pd.notna(max_dt):
            if date_range == "30d":
                cutoff = max_dt - datetime.timedelta(days=30)
                df = df[df["parsed_date"] >= cutoff]
            elif date_range == "90d":
                cutoff = max_dt - datetime.timedelta(days=90)
                df = df[df["parsed_date"] >= cutoff]
            elif date_range == "180d":
                cutoff = max_dt - datetime.timedelta(days=180)
                df = df[df["parsed_date"] >= cutoff]
            elif date_range == "ytd":
                cutoff = pd.Timestamp(year=max_dt.year, month=1, day=1)
                df = df[df["parsed_date"] >= cutoff]
            elif date_range == "custom" and from_date:
                f_dt = pd.to_datetime(from_date, errors="coerce")
                if pd.notna(f_dt):
                    df = df[df["parsed_date"] >= f_dt]
                if to_date:
                    t_dt = pd.to_datetime(to_date, errors="coerce")
                    if pd.notna(t_dt):
                        df = df[df["parsed_date"] <= t_dt]

    return df

def _infer_category_nature(category_name: str) -> str:
    """
    Dynamically and intelligently maps any category name (standard, custom, or user-created)
    to its 50/30/20 financial nature: 'needs', 'wants', 'investments', 'transfers', or 'income'.
    """
    if not category_name or not str(category_name).strip():
        return "wants"
    
    c = str(category_name).strip().lower()
    
    exact_map = {
        "utilities & bills": "needs",
        "loans & emi": "needs",
        "health & medical": "needs",
        "taxes": "needs",
        "bank charges & fees": "needs",
        "food & dining": "wants",
        "shopping & groceries": "wants",
        "entertainment": "wants",
        "travel & transport": "wants",
        "investments": "investments",
        "salary/income": "income",
        "interest Income": "income",
        "transfers & payments": "transfers",
        "cash withdrawal": "transfers",
    }
    if c in exact_map:
        return exact_map[c]
        
    if any(k in c for k in ("utilit", "bill", "electr", "water", "gas", "recharge", "wifi", "rent", "emi", "loan", "mortgage", "insur", "medic", "health", "doctor", "pharm", "tax", "gst", "tds", "fee", "charg", "grocer", "ration")):
        return "needs"
        
    if any(k in c for k in ("invest", "sip", "fund", "stock", "equity", "demat", "groww", "zerodha", "nps", "ppf", "fd", "gold", "crypto", "wealth")):
        return "investments"
        
    if any(k in c for k in ("transfer", "tfr", "atm", "cash", "self", "card pay", "credit card pay", "cc bill", "settle")):
        return "transfers"
        
    if any(k in c for k in ("salary", "wage", "payroll", "dividend", "interest", "refund", "cashback", "credit interest")):
        return "income"
        
    if any(k in c for k in ("dine", "dining", "food", "restaurant", "swiggy", "zomato", "cafe", "coffee", "shop", "apparel", "cloth", "fashion", "movie", "cinema", "netflix", "ott", "game", "travel", "flight", "hotel", "trip", "vacation", "cab", "uber", "ola", "lifestyle", "hobby")):
        return "wants"
        
    return "wants"

@router.get("/{session_id}/overview")
async def get_budget_overview(
    session_id: str,
    bank: Optional[str] = None,
    account_type: Optional[str] = None,
    txn_type: Optional[str] = None,
    date_range: Optional[str] = "all",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    amount_bracket: Optional[str] = "all",
    payment_mode: Optional[str] = "all",
    category: Optional[str] = "all",
    search: Optional[str] = None
):
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(401, detail="Unauthorized")
    identity.owns_record(user_id)
    
    if session_id == "overall":
        df, accounts = get_all_budget_sessions(user_id)
    else:
        df, accounts = get_budget_session(session_id)
        
    if df.empty:
        raise HTTPException(404, detail="Session not found or empty")

    # Extract all unique banks, account types, and categories before any filtering
    all_banks = []
    if "source_bank" in df.columns:
        all_banks = sorted(list({str(b).strip().upper() for b in df["source_bank"].unique() if pd.notna(b) and str(b).strip() and str(b).strip().upper() != "UNKNOWN"}))

    all_account_types = []
    if "account_type" in df.columns:
        all_account_types = sorted(list({str(a).strip() for a in df["account_type"].unique() if pd.notna(a) and str(a).strip()}))
    if not all_account_types:
        all_account_types = ["Savings Account"]

    all_categories = []
    if "category" in df.columns:
        all_categories = sorted(list({str(c).strip() for c in df["category"].dropna().unique() if str(c).strip() and str(c).strip().lower() != "nan"}))

    # Calculate Bank & Account Breakdown across all available banks
    bank_breakdown = []
    if "source_bank" in df.columns:
        for b in all_banks:
            b_df = df[df["source_bank"] == b]
            b_acc_types = sorted(b_df["account_type"].dropna().unique().tolist()) if "account_type" in b_df.columns else ["Savings Account"]
            b_acc_type_label = ", ".join(b_acc_types) if b_acc_types else "Savings Account"
            b_inc = float(b_df[b_df["type"] == "credit"]["amount"].sum())
            b_exp = float(b_df[b_df["type"] == "debit"]["amount"].sum())
            bank_breakdown.append({
                "bank": b,
                "account_type": b_acc_type_label,
                "income": b_inc,
                "expense": b_exp,
                "net": b_inc - b_exp,
                "transactions": len(b_df)
            })

    # Apply all unified filters
    df = _apply_budget_filters(
        df, 
        bank=bank, 
        account_type=account_type, 
        txn_type=txn_type,
        date_range=date_range, 
        from_date=from_date, 
        to_date=to_date,
        amount_bracket=amount_bracket,
        payment_mode=payment_mode,
        category=category,
        search=search
    )

    if df.empty:
        return {
            "total_income": 0.0,
            "total_expense": 0.0,
            "total_credits": 0.0,
            "total_debits": 0.0,
            "net_savings": 0.0,
            "savings_rate": 0.0,
            "monthly_trend": [],
            "cumulative_trend": [],
            "top_merchants": [],
            "day_of_week_spend": [],
            "health_metrics": {
                "avg_monthly_burn": 0.0,
                "avg_daily_spend": 0.0,
                "largest_debit": None,
                "largest_credit": None,
                "total_days": 0,
                "active_months": 0
            },
            "biggest_change": None,
            "recurring_charges": [],
            "banks": all_banks,
            "account_types": all_account_types,
            "categories": all_categories,
            "bank_breakdown": bank_breakdown
        }
        
    total_income = float(df[df["type"] == "credit"]["amount"].sum())
    total_expense = float(df[df["type"] == "debit"]["amount"].sum())
    net_savings = total_income - total_expense
    savings_rate = (net_savings / total_income * 100) if total_income > 0 else 0
    
    # Calculate Monthly Trend
    monthly_trend = []
    if not df.empty and "date" in df.columns:
        df["parsed_date"] = pd.to_datetime(df["date"], errors="coerce")
        df_valid_dates = df.dropna(subset=["parsed_date"]).copy()
        
        if not df_valid_dates.empty:
            df_valid_dates["month"] = df_valid_dates["parsed_date"].dt.strftime("%Y-%m")
            
            income_df = df_valid_dates[df_valid_dates["type"] == "credit"]
            expense_df = df_valid_dates[df_valid_dates["type"] == "debit"]
            
            months = sorted(df_valid_dates["month"].unique())
            for m in months:
                inc = income_df[income_df["month"] == m]["amount"].sum() if not income_df.empty else 0
                exp = expense_df[expense_df["month"] == m]["amount"].sum() if not expense_df.empty else 0
                monthly_trend.append({
                    "month": m,
                    "income": float(inc),
                    "expense": float(exp)
                })
            
    # Top Merchants / Payees Breakdown
    top_merchants = []
    expenses_df = df[df["type"] == "debit"].copy()
    if not expenses_df.empty:
        expenses_df["merchant"] = expenses_df["description"].apply(_clean_merchant_name)
        m_grouped = expenses_df.groupby("merchant").agg(
            total_amount=("amount", "sum"),
            tx_count=("amount", "count")
        ).reset_index()
        m_grouped = m_grouped.sort_values(by="total_amount", ascending=False).head(10)
        for _, mr in m_grouped.iterrows():
            top_merchants.append({
                "merchant": str(mr["merchant"]),
                "amount": float(mr["total_amount"]),
                "count": int(mr["tx_count"])
            })

    # Top Inflows Breakdown
    top_inflows = []
    inflow_df = df[df["type"] == "credit"].copy()
    if not inflow_df.empty:
        inflow_df["merchant"] = inflow_df["description"].apply(_clean_merchant_name)
        in_grouped = inflow_df.groupby("merchant").agg(
            total_amount=("amount", "sum"),
            tx_count=("amount", "count")
        ).reset_index()
        in_grouped = in_grouped.sort_values(by="total_amount", ascending=False).head(10)
        for _, mr in in_grouped.iterrows():
            top_inflows.append({
                "merchant": str(mr["merchant"]),
                "amount": float(mr["total_amount"]),
                "count": int(mr["tx_count"])
            })

    # Cumulative Cash Flow Trajectory & Day of Week Spending
    cumulative_trend = []
    day_of_week_spend = []
    
    if not df.empty and "parsed_date" in df.columns:
        df_sorted = df.dropna(subset=["parsed_date"]).sort_values(by="parsed_date").copy()
        if not df_sorted.empty:
            # 1. Day of Week
            df_sorted["dow"] = df_sorted["parsed_date"].dt.day_name()
            df_sorted["dow_num"] = df_sorted["parsed_date"].dt.dayofweek
            dow_expenses = df_sorted[df_sorted["type"] == "debit"]
            
            dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            dow_map = {d: 0.0 for d in dow_order}
            dow_count_map = {d: 0 for d in dow_order}
            
            if not dow_expenses.empty:
                dow_grp = dow_expenses.groupby("dow").agg(amount=("amount", "sum"), count=("amount", "count"))
                for d, r in dow_grp.iterrows():
                    dow_map[d] = float(r["amount"])
                    dow_count_map[d] = int(r["count"])
                    
            for d in dow_order:
                sp = dow_map[d]
                ct = dow_count_map[d]
                day_of_week_spend.append({
                    "day": d[:3],
                    "spend": sp,
                    "count": ct,
                    "avg_spend": (sp / ct) if ct > 0 else 0.0
                })

            # 2. Cumulative Trajectory (grouped daily or monthly depending on size)
            df_sorted["date_str"] = df_sorted["parsed_date"].dt.strftime("%Y-%m-%d")
            daily_flow = df_sorted.groupby("date_str").apply(
                lambda x: float(x[x["type"] == "credit"]["amount"].sum() - x[x["type"] == "debit"]["amount"].sum())
            ).reset_index(name="net")
            
            daily_flow["cumulative"] = daily_flow["net"].cumsum()
            # Downsample if too many points (> 60) for smooth rendering
            step = max(1, len(daily_flow) // 50)
            sampled = daily_flow.iloc[::step]
            if len(daily_flow) > 0 and (len(sampled) == 0 or sampled.iloc[-1]["date_str"] != daily_flow.iloc[-1]["date_str"]):
                sampled = pd.concat([sampled, daily_flow.iloc[[-1]]])
                
            for _, cr in sampled.iterrows():
                cumulative_trend.append({
                    "date": cr["date_str"],
                    "net": float(cr["net"]),
                    "cumulative": float(cr["cumulative"])
                })

    # Health & Benchmark Metrics
    active_months_count = len(monthly_trend) if monthly_trend else 1
    avg_monthly_burn = (total_expense / active_months_count) if active_months_count > 0 else total_expense
    
    total_days = 1
    if not df.empty and "parsed_date" in df.columns:
        valid_dts = df["parsed_date"].dropna()
        if len(valid_dts) > 0:
            total_days = max(1, (valid_dts.max() - valid_dts.min()).days + 1)
    avg_daily_spend = total_expense / total_days

    largest_debit = None
    if not expenses_df.empty:
        max_d = expenses_df.loc[expenses_df["amount"].idxmax()]
        largest_debit = {
            "description": str(max_d.get("description", "")),
            "amount": float(max_d.get("amount", 0)),
            "date": str(max_d.get("date", ""))
        }

    credits_df = df[df["type"] == "credit"]
    largest_credit = None
    if not credits_df.empty:
        max_c = credits_df.loc[credits_df["amount"].idxmax()]
        largest_credit = {
            "description": str(max_c.get("description", "")),
            "amount": float(max_c.get("amount", 0)),
            "date": str(max_c.get("date", ""))
        }

    health_metrics = {
        "avg_monthly_burn": float(avg_monthly_burn),
        "avg_daily_spend": float(avg_daily_spend),
        "largest_debit": largest_debit,
        "largest_credit": largest_credit,
        "total_days": int(total_days),
        "active_months": int(active_months_count)
    }

    # Advanced Analytics: Biggest Changes & Recurring Charges
    biggest_change = None
    recurring_charges = []
    
    if not df.empty and "parsed_date" in df.columns:
        df_valid = df.dropna(subset=["parsed_date"]).copy()
        if not df_valid.empty:
            df_valid = df_valid.sort_values(by="parsed_date")
            expenses = df_valid[df_valid["type"] == "debit"]
            counts = expenses.groupby(["description", "amount"]).size().reset_index(name="count")
            recurring = counts[counts["count"] >= 2].sort_values(by="count", ascending=False)
            
            for _, r in recurring.head(5).iterrows():
                recurring_charges.append({
                    "description": r["description"],
                    "amount": float(r["amount"]),
                    "frequency": int(r["count"])
                })
                
            max_date = df_valid["parsed_date"].max()
            last_30 = max_date - datetime.timedelta(days=30)
            prev_30 = max_date - datetime.timedelta(days=60)
            
            recent_exp = expenses[expenses["parsed_date"] > last_30].groupby("category")["amount"].sum()
            prev_exp = expenses[(expenses["parsed_date"] <= last_30) & (expenses["parsed_date"] > prev_30)].groupby("category")["amount"].sum()
            
            diffs = recent_exp.subtract(prev_exp, fill_value=0)
            if not diffs.empty:
                biggest_cat = diffs.idxmax()
                val = float(diffs.max())
                if val > 0:
                    biggest_change = {
                        "category": biggest_cat,
                        "increase_amount": val
                    }

    # 50/30/20 Comprehensive Budget Evaluation Engine
    base_benchmark = total_income if total_income > 0 else total_expense
    needs_amount = 0.0
    wants_amount = 0.0
    direct_investments = 0.0
    transfers_amount = 0.0
    
    needs_cats = {}
    wants_cats = {}
    inv_cats = {}
    
    for _, row in expenses_df.iterrows():
        cat = str(row.get("category", "Uncategorized"))
        amt = float(row.get("amount", 0.0))
        nat = _infer_category_nature(cat)
        
        if nat == "needs":
            needs_amount += amt
            needs_cats[cat] = needs_cats.get(cat, 0.0) + amt
        elif nat == "investments":
            direct_investments += amt
            inv_cats[cat] = inv_cats.get(cat, 0.0) + amt
        elif nat == "transfers":
            transfers_amount += amt
        else:
            wants_amount += amt
            wants_cats[cat] = wants_cats.get(cat, 0.0) + amt

    surplus_savings = max(0.0, total_income - total_expense) if total_income > 0 else 0.0
    total_invested_and_saved = direct_investments + surplus_savings
    
    needs_pct = (needs_amount / base_benchmark * 100) if base_benchmark > 0 else 0.0
    wants_pct = (wants_amount / base_benchmark * 100) if base_benchmark > 0 else 0.0
    inv_pct = (total_invested_and_saved / base_benchmark * 100) if base_benchmark > 0 else 0.0
    
    # Financial Health Scoring (0 - 100)
    score_needs = 40.0 * max(0.0, min(1.0, 1.0 - max(0.0, needs_pct - 50.0) / 30.0))
    score_wants = 30.0 * max(0.0, min(1.0, 1.0 - max(0.0, wants_pct - 30.0) / 30.0))
    score_savings = 30.0 * min(1.0, inv_pct / 20.0)
    overall_health_score = int(round(score_needs + score_wants + score_savings))
    
    recommendations = []
    if needs_pct > 50:
        recommendations.append(f"Fixed essentials ({needs_pct:.1f}%) exceed the 50% target by ₹{(needs_amount - 0.5 * base_benchmark):,.0f}. Audit utilities and loan interest rates.")
    if wants_pct > 30:
        recommendations.append(f"Discretionary spends ({wants_pct:.1f}%) exceed the 30% target by ₹{(wants_amount - 0.3 * base_benchmark):,.0f}. Trimming dining/shopping can accelerate wealth creation.")
    if inv_pct < 20:
        recommendations.append(f"Savings & investment rate is {inv_pct:.1f}% (Target ≥ 20%). Try setting up auto-debit SIPs at the start of the month.")
    if not recommendations:
        recommendations.append("Outstanding financial discipline! Your spending and savings adhere excellently to the 50/30/20 benchmark.")

    budget_50_30_20 = {
        "health_score": overall_health_score,
        "base_amount": base_benchmark,
        "base_type": "income" if total_income > 0 else "expense",
        "needs": {
            "amount": needs_amount,
            "percentage": needs_pct,
            "target_pct": 50.0,
            "target_amount": 0.50 * base_benchmark,
            "status": "optimal" if needs_pct <= 50.0 else "warning" if needs_pct <= 60.0 else "critical",
            "categories": [{"name": k, "amount": v} for k, v in sorted(needs_cats.items(), key=lambda x: x[1], reverse=True)]
        },
        "wants": {
            "amount": wants_amount,
            "percentage": wants_pct,
            "target_pct": 30.0,
            "target_amount": 0.30 * base_benchmark,
            "status": "optimal" if wants_pct <= 30.0 else "warning" if wants_pct <= 40.0 else "critical",
            "categories": [{"name": k, "amount": v} for k, v in sorted(wants_cats.items(), key=lambda x: x[1], reverse=True)]
        },
        "investments": {
            "amount": total_invested_and_saved,
            "direct_investments": direct_investments,
            "surplus_savings": surplus_savings,
            "percentage": inv_pct,
            "target_pct": 20.0,
            "target_amount": 0.20 * base_benchmark,
            "status": "optimal" if inv_pct >= 20.0 else "warning" if inv_pct >= 10.0 else "critical",
            "categories": [{"name": k, "amount": v} for k, v in sorted(inv_cats.items(), key=lambda x: x[1], reverse=True)]
        },
        "transfers_amount": transfers_amount,
        "recommendations": recommendations
    }

    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "total_credits": total_income,
        "total_debits": total_expense,
        "net_savings": net_savings,
        "savings_rate": savings_rate,
        "monthly_trend": monthly_trend,
        "cumulative_trend": cumulative_trend,
        "top_merchants": top_merchants,
        "top_inflows": top_inflows,
        "day_of_week_spend": day_of_week_spend,
        "health_metrics": health_metrics,
        "biggest_change": biggest_change,
        "recurring_charges": recurring_charges,
        "banks": all_banks,
        "account_types": all_account_types,
        "categories": all_categories,
        "bank_breakdown": bank_breakdown,
        "budget_50_30_20": budget_50_30_20
    }

@router.get("/{session_id}/transactions")
async def get_transactions(
    session_id: str,
    bank: Optional[str] = None,
    account_type: Optional[str] = None,
    txn_type: Optional[str] = None,
    date_range: Optional[str] = "all",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    amount_bracket: Optional[str] = "all",
    payment_mode: Optional[str] = "all",
    category: Optional[str] = "all",
    search: Optional[str] = None
):
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(401, detail="Unauthorized")
    identity.owns_record(user_id)
    
    if session_id == "overall":
        df, _ = get_all_budget_sessions(user_id)
    else:
        df, _ = get_budget_session(session_id)
        
    if df.empty:
        return {"transactions": []}

    df = _apply_budget_filters(
        df,
        bank=bank,
        account_type=account_type,
        txn_type=txn_type,
        date_range=date_range,
        from_date=from_date,
        to_date=to_date,
        amount_bracket=amount_bracket,
        payment_mode=payment_mode,
        category=category,
        search=search
    )
        
    return {"transactions": df.fillna("").to_dict(orient="records")}

@router.get("/{session_id}/categories")
async def get_category_breakdown(
    session_id: str,
    bank: Optional[str] = None,
    account_type: Optional[str] = None,
    txn_type: Optional[str] = None,
    date_range: Optional[str] = "all",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    amount_bracket: Optional[str] = "all",
    payment_mode: Optional[str] = "all",
    category: Optional[str] = "all",
    search: Optional[str] = None
):
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(401, detail="Unauthorized")
    identity.owns_record(user_id)
    
    if session_id == "overall":
        df, _ = get_all_budget_sessions(user_id)
    else:
        df, _ = get_budget_session(session_id)
        
    # Keep unfiltered copy for total reference and all categories list
    all_available_categories = sorted(df[df["type"] == (txn_type.lower() if txn_type in ("debit", "credit") else "debit")]["category"].dropna().unique().tolist())
    overall_total_spend = float(df[df["type"] == (txn_type.lower() if txn_type in ("debit", "credit") else "debit")]["amount"].sum())

    df = _apply_budget_filters(
        df,
        bank=bank,
        account_type=account_type,
        txn_type=txn_type,
        date_range=date_range,
        from_date=from_date,
        to_date=to_date,
        amount_bracket=amount_bracket,
        payment_mode=payment_mode,
        category=category,
        search=search
    )
        
    target_type = txn_type.lower() if txn_type and txn_type.lower() in ("debit", "credit") else "debit"
    target_df = df[df["type"] == target_type].copy()
    if target_df.empty:
        return {
            "is_drilldown": False,
            "selected_category": category if category != "all" else None,
            "all_categories": all_available_categories,
            "categories": [], 
            "nature_summary": {"needs": 0.0, "wants": 0.0, "investments": 0.0, "other": 0.0},
            "total_amount": 0.0
        }
        
    target_df["merchant"] = target_df["description"].apply(_clean_merchant_name)
    total_spend = float(target_df["amount"].sum())
    
    # IF A SPECIFIC CATEGORY IS SELECTED: Return Deep Drill-down Mode
    if category and category != "all":
        cat_amount = total_spend
        cat_count = len(target_df)
        avg_ticket = cat_amount / cat_count if cat_count > 0 else 0.0
        nature = _infer_category_nature(category)
        
        # Merchants breakdown within this category
        merchant_records = []
        for m_name, m_grp in target_df.groupby("merchant"):
            m_amt = float(m_grp["amount"].sum())
            m_cnt = int(len(m_grp))
            merchant_records.append({
                "merchant": str(m_name),
                "amount": m_amt,
                "count": m_cnt,
                "percentage": (m_amt / cat_amount * 100) if cat_amount > 0 else 0.0,
                "avg_ticket": m_amt / m_cnt if m_cnt > 0 else 0.0
            })
        merchant_records = sorted(merchant_records, key=lambda x: x["amount"], reverse=True)
        
        # Monthly progression for this category
        monthly_trend = []
        try:
            target_df["month"] = pd.to_datetime(target_df["date"], errors="coerce").dt.strftime("%b %Y")
            m_grouped = target_df.dropna(subset=["month"]).groupby("month", sort=False)["amount"].sum().reset_index()
            monthly_trend = m_grouped.to_dict(orient="records")
        except:
            pass
            
        # Largest transaction in this category
        largest_row = target_df.sort_values(by="amount", ascending=False).iloc[0].to_dict() if not target_df.empty else None
        largest_txn = {
            "description": str(largest_row.get("description", "")),
            "amount": float(largest_row.get("amount", 0.0)),
            "date": str(largest_row.get("date", "")),
            "bank": str(largest_row.get("bank", ""))
        } if largest_row else None

        return {
            "is_drilldown": True,
            "selected_category": category,
            "all_categories": all_available_categories,
            "category_stats": {
                "category": category,
                "amount": cat_amount,
                "count": cat_count,
                "avg_ticket": avg_ticket,
                "nature": nature,
                "percentage_of_total": (cat_amount / overall_total_spend * 100) if overall_total_spend > 0 else 100.0,
                "merchants": merchant_records,
                "monthly_trend": monthly_trend,
                "largest_txn": largest_txn
            },
            "total_amount": cat_amount
        }

    # DEFAULT: Return Multi-Category Breakdown
    cat_records = []
    nature_sums = {"needs": 0.0, "wants": 0.0, "investments": 0.0, "transfers": 0.0, "other": 0.0}
    nature_counts = {"needs": 0, "wants": 0, "investments": 0, "transfers": 0, "other": 0}
    
    for cat_name, group in target_df.groupby("category"):
        cat_str = str(cat_name)
        cat_amount = float(group["amount"].sum())
        cat_count = int(len(group))
        nature = _infer_category_nature(cat_str)
        
        if nature in nature_sums:
            nature_sums[nature] += cat_amount
            nature_counts[nature] += 1
        else:
            nature_sums["other"] += cat_amount
            nature_counts["other"] += 1
            
        top_m = group.groupby("merchant")["amount"].sum().sort_values(ascending=False).head(3).to_dict()
        top_merchants_formatted = [{"name": k, "amount": float(v)} for k, v in top_m.items()]
        
        cat_records.append({
            "category": cat_str,
            "amount": cat_amount,
            "count": cat_count,
            "avg_ticket": cat_amount / cat_count if cat_count > 0 else 0.0,
            "percentage": (cat_amount / total_spend * 100) if total_spend > 0 else 0.0,
            "nature": nature,
            "top_merchants": top_merchants_formatted
        })
        
    cat_records = sorted(cat_records, key=lambda x: x["amount"], reverse=True)
    
    # Build Dynamic Available Natures List (Only for natures that exist!)
    NATURE_METADATA = {
        "needs": {"label": "Needs (Fixed)", "icon": "🛡️", "color": "#38bdf8"},
        "wants": {"label": "Wants (Lifestyle)", "icon": "🎯", "color": "#f472b6"},
        "investments": {"label": "Investments", "icon": "📈", "color": "#34d399"},
        "transfers": {"label": "Transfers & Cash", "icon": "🔄", "color": "#a78bfa"},
        "other": {"label": "Other / Custom", "icon": "🏷️", "color": "#cbd5e1"}
    }
    
    available_natures = []
    for nat_key, nat_amt in nature_sums.items():
        if nat_amt > 0 or nature_counts.get(nat_key, 0) > 0:
            meta = NATURE_METADATA.get(nat_key, {"label": nat_key.capitalize(), "icon": "🏷️", "color": "#cbd5e1"})
            available_natures.append({
                "nature": nat_key,
                "label": meta["label"],
                "icon": meta["icon"],
                "color": meta["color"],
                "count": nature_counts.get(nat_key, 0),
                "amount": nat_amt
            })
    
    return {
        "is_drilldown": False,
        "selected_category": None,
        "all_categories": all_available_categories,
        "categories": cat_records,
        "available_natures": available_natures,
        "nature_summary": nature_sums,
        "total_amount": total_spend
    }

class TransactionUpdate(BaseModel):
    txn_id: str
    session_id: str
    category: Optional[str] = None
    notes: Optional[str] = None

@router.put("/transactions/update")
async def bulk_update_transactions(
    updates: List[TransactionUpdate] = Body(...)
):
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(401, detail="Unauthorized")
    identity.owns_record(user_id)
    
    # Group updates by session_id
    from collections import defaultdict
    session_updates = defaultdict(list)
    for u in updates:
        session_updates[u.session_id].append({
            "txn_id": u.txn_id,
            "category": u.category,
            "notes": u.notes
        })
        
    for sid, txns in session_updates.items():
        success = update_budget_transactions(user_id, sid, txns)
        if not success:
            raise HTTPException(400, detail=f"Failed to update session {sid}")
            
    return {"status": "ok"}
