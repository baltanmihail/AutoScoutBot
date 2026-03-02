"""
Financial ratio computation from BFO (Russian financial statements) line codes.

Takes a dict of {year: {code: value, ...}} and computes 40+ ratios
that a real financial analyst would use to evaluate a company.

BFO line codes reference:
  Form 1 (Balance Sheet):
    1100 Non-current assets       1200 Current assets
    1110 Intangible assets        1210 Inventories
    1120 R&D results              1220 VAT on acquired assets
    1150 Fixed assets             1230 Receivables
    1170 Long-term investments    1240 Short-term investments
    1250 Cash & equivalents       1260 Other current assets
    1300 Equity                   1310 Authorized capital
    1370 Retained earnings        1400 Long-term liabilities
    1410 Long-term borrowings     1500 Short-term liabilities
    1510 Short-term borrowings    1520 Accounts payable
    1600 Total assets             1700 Total equity & liabilities

  Form 2 (Income Statement):
    2110 Revenue                  2120 Cost of sales
    2100 Gross profit             2200 Operating profit
    2210 Selling expenses         2220 Administrative expenses
    2300 Profit before tax        2330 Interest payable
    2400 Net profit               2500 Comprehensive result
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import numpy as np


def _g(data: dict, code: str, default: float = 0.0) -> float:
    """Get BFO value by line code."""
    val = data.get(code, default)
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_div(a: float, b: float) -> float:
    """Safe division, returns 0 if denominator is 0."""
    if b == 0:
        return 0.0
    return a / b


def compute_ratios_for_year(data: dict) -> Dict[str, float]:
    """
    Compute all financial ratios from a single year's BFO data.
    Returns dict of ratio_name -> value.
    """
    r: Dict[str, float] = {}

    # Raw values
    total_assets = _g(data, "1600") or _g(data, "total_assets")
    equity = _g(data, "1300") or _g(data, "equity")
    current_assets = _g(data, "1200") or _g(data, "current_assets")
    non_current_assets = _g(data, "1100") or _g(data, "non_current_assets")
    current_liabilities = _g(data, "1500") or _g(data, "current_liabilities")
    long_term_liabilities = _g(data, "1400")
    total_liabilities = long_term_liabilities + current_liabilities

    inventories = _g(data, "1210")
    receivables = _g(data, "1230")
    cash = _g(data, "1250") or _g(data, "cash")
    short_investments = _g(data, "1240")

    intangible_assets = _g(data, "1110")
    rd_results = _g(data, "1120")
    fixed_assets = _g(data, "1150") or _g(data, "fixed_assets")
    long_investments = _g(data, "1170")

    authorized_capital = _g(data, "1310")
    retained_earnings = _g(data, "1370") or _g(data, "retained_earnings")
    long_borrowings = _g(data, "1410")
    short_borrowings = _g(data, "1510")
    accounts_payable = _g(data, "1520")

    revenue = _g(data, "2110") or _g(data, "revenue")
    cost_of_sales = _g(data, "2120") or _g(data, "cost_of_sales")
    gross_profit = _g(data, "2100") or _g(data, "gross_profit")
    operating_profit = _g(data, "2200") or _g(data, "operating_profit")
    selling_expenses = _g(data, "2210")
    admin_expenses = _g(data, "2220")
    profit_before_tax = _g(data, "2300")
    interest_payable = _g(data, "2330")
    net_profit = _g(data, "2400") or _g(data, "net_profit")

    # ===================================================================
    # I. LIQUIDITY (can the company pay its short-term debts?)
    # ===================================================================
    r["current_ratio"] = _safe_div(current_assets, current_liabilities)
    r["quick_ratio"] = _safe_div(current_assets - inventories, current_liabilities)
    r["cash_ratio"] = _safe_div(cash + short_investments, current_liabilities)
    r["cash_to_current_liab"] = _safe_div(cash, current_liabilities)

    working_capital = current_assets - current_liabilities
    r["working_capital_log"] = np.sign(working_capital) * np.log1p(abs(working_capital))
    r["working_capital_to_assets"] = _safe_div(working_capital, total_assets)

    # ===================================================================
    # II. SOLVENCY / FINANCIAL STABILITY
    # ===================================================================
    r["equity_ratio"] = _safe_div(equity, total_assets)
    r["debt_to_equity"] = _safe_div(total_liabilities, equity) if equity > 0 else 10.0
    r["debt_to_assets"] = _safe_div(total_liabilities, total_assets)
    r["long_term_debt_share"] = _safe_div(long_term_liabilities, long_term_liabilities + equity) if (long_term_liabilities + equity) > 0 else 0.0
    r["financial_leverage"] = _safe_div(total_assets, equity) if equity > 0 else 10.0
    r["interest_coverage"] = _safe_div(operating_profit, interest_payable) if interest_payable > 0 else 0.0
    r["borrowings_to_assets"] = _safe_div(long_borrowings + short_borrowings, total_assets)
    r["equity_to_debt"] = _safe_div(equity, total_liabilities) if total_liabilities > 0 else 10.0

    # ===================================================================
    # III. PROFITABILITY
    # ===================================================================
    r["gross_margin"] = _safe_div(gross_profit, revenue)
    r["operating_margin"] = _safe_div(operating_profit, revenue)
    r["net_margin"] = _safe_div(net_profit, revenue)
    r["roa"] = _safe_div(net_profit, total_assets)
    r["roe"] = _safe_div(net_profit, equity) if equity > 0 else 0.0
    r["cost_to_revenue"] = _safe_div(cost_of_sales, revenue)
    r["opex_ratio"] = _safe_div(selling_expenses + admin_expenses, revenue)

    # ===================================================================
    # IV. EFFICIENCY / TURNOVER
    # ===================================================================
    r["asset_turnover"] = _safe_div(revenue, total_assets)
    r["receivables_turnover"] = _safe_div(revenue, receivables) if receivables > 0 else 0.0
    r["inventory_turnover"] = _safe_div(abs(cost_of_sales), inventories) if inventories > 0 else 0.0
    r["payables_turnover"] = _safe_div(abs(cost_of_sales), accounts_payable) if accounts_payable > 0 else 0.0
    r["receivables_days"] = _safe_div(receivables * 365, revenue) if revenue > 0 else 0.0
    r["payables_days"] = _safe_div(accounts_payable * 365, abs(cost_of_sales)) if cost_of_sales != 0 else 0.0

    # ===================================================================
    # V. ASSET STRUCTURE (what is the company made of?)
    # ===================================================================
    r["non_current_share"] = _safe_div(non_current_assets, total_assets)
    r["current_share"] = _safe_div(current_assets, total_assets)
    r["cash_share"] = _safe_div(cash, total_assets)
    r["receivables_share"] = _safe_div(receivables, total_assets)
    r["inventory_share"] = _safe_div(inventories, total_assets)
    r["intangible_share"] = _safe_div(intangible_assets, total_assets)
    r["rd_share"] = _safe_div(rd_results, total_assets)
    r["fixed_assets_share"] = _safe_div(fixed_assets, total_assets)

    # ===================================================================
    # VI. BANKRUPTCY PREDICTION (Altman Z-score, adapted)
    # ===================================================================
    if total_assets > 0:
        x1 = _safe_div(working_capital, total_assets)
        x2 = _safe_div(retained_earnings, total_assets)
        x3 = _safe_div(operating_profit or profit_before_tax, total_assets)
        x4 = _safe_div(equity, total_liabilities) if total_liabilities > 0 else 1.0
        x5 = _safe_div(revenue, total_assets)
        r["altman_z"] = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
    else:
        r["altman_z"] = 0.0

    # Taffler model (UK-adapted)
    if current_liabilities > 0 and total_assets > 0:
        t1 = _safe_div(operating_profit, current_liabilities)
        t2 = _safe_div(current_assets, total_liabilities) if total_liabilities > 0 else 1.0
        t3 = _safe_div(current_liabilities, total_assets)
        t4 = _safe_div(revenue, total_assets)
        r["taffler_z"] = 0.53 * t1 + 0.13 * t2 + 0.18 * t3 + 0.16 * t4
    else:
        r["taffler_z"] = 0.0

    # ===================================================================
    # VII. RISK FLAGS (binary indicators)
    # ===================================================================
    r["negative_equity"] = 1.0 if equity < 0 else 0.0
    r["loss_making"] = 1.0 if net_profit < 0 else 0.0
    r["overlevered"] = 1.0 if (equity > 0 and _safe_div(total_liabilities, equity) > 5) else (1.0 if equity <= 0 else 0.0)
    r["zero_revenue"] = 1.0 if revenue == 0 else 0.0
    r["negative_working_capital"] = 1.0 if working_capital < 0 else 0.0

    # ===================================================================
    # VIII. SCALE & MAGNITUDE (log-scaled)
    # ===================================================================
    r["log_revenue"] = np.sign(revenue) * np.log1p(abs(revenue))
    r["log_net_profit"] = np.sign(net_profit) * np.log1p(abs(net_profit))
    r["log_total_assets"] = np.log1p(abs(total_assets))
    r["log_equity"] = np.sign(equity) * np.log1p(abs(equity))
    r["log_cash"] = np.log1p(abs(cash))

    return r


def compute_dynamic_ratios(
    financials: Dict[int, dict],
    target_year: Optional[int] = None,
) -> Dict[str, float]:
    """
    Compute growth/trend metrics across multiple years.

    Args:
        financials: {year: {code: value, ...}} from Checko
        target_year: if None, uses the latest available year
    """
    if not financials:
        return {}

    years = sorted(financials.keys())
    if not years:
        return {}

    if target_year is None:
        target_year = max(years)

    r: Dict[str, float] = {}

    # Revenue series
    rev_series = [(y, _g(financials[y], "2110") or _g(financials[y], "revenue")) for y in years]
    rev_series = [(y, v) for y, v in rev_series if v > 0]

    # Revenue YoY growth (latest)
    if len(rev_series) >= 2:
        y2, v2 = rev_series[-1]
        y1, v1 = rev_series[-2]
        r["revenue_yoy"] = _safe_div(v2 - v1, abs(v1))
    else:
        r["revenue_yoy"] = 0.0

    # Revenue CAGR
    if len(rev_series) >= 2:
        first_y, first_v = rev_series[0]
        last_y, last_v = rev_series[-1]
        n_years = last_y - first_y
        if n_years > 0 and first_v > 0 and last_v > 0:
            r["revenue_cagr"] = (last_v / first_v) ** (1.0 / n_years) - 1.0
        else:
            r["revenue_cagr"] = 0.0
    else:
        r["revenue_cagr"] = 0.0

    # Profit trend (improving/declining)
    profit_series = [(y, _g(financials[y], "2400") or _g(financials[y], "net_profit")) for y in years]
    profit_vals = [v for _, v in profit_series if v != 0]
    if len(profit_vals) >= 2:
        recent = profit_vals[-1]
        older = profit_vals[0]
        r["profit_trend"] = 1.0 if recent > older else (-1.0 if recent < older else 0.0)
    else:
        r["profit_trend"] = 0.0

    # Profit YoY
    profit_nonzero = [(y, v) for y, v in profit_series if v != 0]
    if len(profit_nonzero) >= 2:
        _, v2 = profit_nonzero[-1]
        _, v1 = profit_nonzero[-2]
        r["profit_yoy"] = _safe_div(v2 - v1, abs(v1))
    else:
        r["profit_yoy"] = 0.0

    # Margin trend
    margins = []
    for y in years:
        rev = _g(financials[y], "2110") or _g(financials[y], "revenue")
        np_ = _g(financials[y], "2400") or _g(financials[y], "net_profit")
        if rev > 0:
            margins.append(np_ / rev)
    if len(margins) >= 2:
        r["margin_trend"] = margins[-1] - margins[0]
        r["margin_volatility"] = float(np.std(margins))
    else:
        r["margin_trend"] = 0.0
        r["margin_volatility"] = 0.0

    # Asset growth
    assets_series = [(y, _g(financials[y], "1600") or _g(financials[y], "total_assets")) for y in years]
    assets_nonzero = [(y, v) for y, v in assets_series if v > 0]
    if len(assets_nonzero) >= 2:
        _, a2 = assets_nonzero[-1]
        _, a1 = assets_nonzero[-2]
        r["asset_growth_yoy"] = _safe_div(a2 - a1, abs(a1))
    else:
        r["asset_growth_yoy"] = 0.0

    # Equity growth
    equity_series = [(y, _g(financials[y], "1300") or _g(financials[y], "equity")) for y in years]
    eq_nonzero = [(y, v) for y, v in equity_series if v != 0]
    if len(eq_nonzero) >= 2:
        _, e2 = eq_nonzero[-1]
        _, e1 = eq_nonzero[-2]
        r["equity_growth_yoy"] = _safe_div(e2 - e1, abs(e1))
    else:
        r["equity_growth_yoy"] = 0.0

    # Years of consecutive revenue
    r["years_with_revenue"] = float(len(rev_series))

    # Years of consecutive profit
    profit_positive = sum(1 for _, v in profit_series if v > 0)
    r["years_profitable"] = float(profit_positive)

    # Years of data total
    r["years_of_data"] = float(len(years))

    return r


# ===================================================================
# Feature names (deterministic order) -- for get_feature_names()
# ===================================================================

BFO_RATIO_NAMES: List[str] = [
    # I. Liquidity (6)
    "bfo_current_ratio",
    "bfo_quick_ratio",
    "bfo_cash_ratio",
    "bfo_cash_to_current_liab",
    "bfo_working_capital_log",
    "bfo_working_capital_to_assets",
    # II. Solvency (8)
    "bfo_equity_ratio",
    "bfo_debt_to_equity",
    "bfo_debt_to_assets",
    "bfo_long_term_debt_share",
    "bfo_financial_leverage",
    "bfo_interest_coverage",
    "bfo_borrowings_to_assets",
    "bfo_equity_to_debt",
    # III. Profitability (7)
    "bfo_gross_margin",
    "bfo_operating_margin",
    "bfo_net_margin",
    "bfo_roa",
    "bfo_roe",
    "bfo_cost_to_revenue",
    "bfo_opex_ratio",
    # IV. Efficiency (6)
    "bfo_asset_turnover",
    "bfo_receivables_turnover",
    "bfo_inventory_turnover",
    "bfo_payables_turnover",
    "bfo_receivables_days",
    "bfo_payables_days",
    # V. Asset structure (8)
    "bfo_non_current_share",
    "bfo_current_share",
    "bfo_cash_share",
    "bfo_receivables_share",
    "bfo_inventory_share",
    "bfo_intangible_share",
    "bfo_rd_share",
    "bfo_fixed_assets_share",
    # VI. Bankruptcy (2)
    "bfo_altman_z",
    "bfo_taffler_z",
    # VII. Risk flags (5)
    "bfo_negative_equity",
    "bfo_loss_making",
    "bfo_overlevered",
    "bfo_zero_revenue",
    "bfo_negative_working_capital",
    # VIII. Scale (5)
    "bfo_log_revenue",
    "bfo_log_net_profit",
    "bfo_log_total_assets",
    "bfo_log_equity",
    "bfo_log_cash",
]

BFO_DYNAMIC_NAMES: List[str] = [
    "bfo_revenue_yoy",
    "bfo_revenue_cagr",
    "bfo_profit_trend",
    "bfo_profit_yoy",
    "bfo_margin_trend",
    "bfo_margin_volatility",
    "bfo_asset_growth_yoy",
    "bfo_equity_growth_yoy",
    "bfo_years_with_revenue",
    "bfo_years_profitable",
    "bfo_years_of_data",
]

ALL_BFO_FEATURE_NAMES: List[str] = BFO_RATIO_NAMES + BFO_DYNAMIC_NAMES


def extract_bfo_features(financials: Dict[int, dict]) -> np.ndarray:
    """
    Extract full BFO feature vector from Checko financials dict.

    Args:
        financials: {year_int: {code_str: value_float, ...}}

    Returns:
        numpy array of len(ALL_BFO_FEATURE_NAMES) = 58 features
    """
    if not financials:
        return np.zeros(len(ALL_BFO_FEATURE_NAMES), dtype=np.float32)

    years = sorted(financials.keys())
    latest_year = max(years)
    latest_data = financials[latest_year]

    static = compute_ratios_for_year(latest_data)
    dynamic = compute_dynamic_ratios(financials)

    feats = []
    for name in BFO_RATIO_NAMES:
        key = name.replace("bfo_", "")
        val = static.get(key, 0.0)
        if not np.isfinite(val):
            val = 0.0
        feats.append(float(np.clip(val, -100, 100)))

    for name in BFO_DYNAMIC_NAMES:
        key = name.replace("bfo_", "")
        val = dynamic.get(key, 0.0)
        if not np.isfinite(val):
            val = 0.0
        feats.append(float(np.clip(val, -100, 100)))

    return np.array(feats, dtype=np.float32)
