"""
Structured report builder for /check command.

Builds a 6-block analytical report:
  1. Company card (facts)
  2. Financial statements (BFO raw data)
  3. Calculated ratios (liquidity, solvency, bankruptcy, profitability)
  4. ML scoring (6 dimensions)
  5. News & media (with sentiment)
  6. AI analytics placeholder (TRL/MRL/IRL assessment prompt)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from utils.formatters import escape_html

logger = logging.getLogger(__name__)


def _fmt_money(val: float) -> str:
    """Format monetary value in human-readable Russian."""
    if val == 0:
        return "0"
    sign = "−" if val < 0 else ""
    v = abs(val)
    if v >= 1_000_000_000:
        return f"{sign}{v / 1_000_000_000:.1f} млрд"
    if v >= 1_000_000:
        return f"{sign}{v / 1_000_000:.1f} млн"
    if v >= 1_000:
        return f"{sign}{v / 1_000:.0f} тыс"
    return f"{sign}{v:.0f}"


def _fmt_pct(val: float) -> str:
    return f"{val * 100:.1f}%"


def _fmt_ratio(val: float) -> str:
    return f"{val:.2f}"


def _traffic_light(value: float, low: float, high: float, inverse: bool = False) -> str:
    """Return emoji for ratio zone. inverse=True means lower is better."""
    if inverse:
        if value <= low:
            return "🟢"
        elif value <= high:
            return "🟡"
        return "🔴"
    if value >= high:
        return "🟢"
    elif value >= low:
        return "🟡"
    return "🔴"


def _altman_verdict(z: float) -> str:
    if z > 2.99:
        return "🟢 безопасная зона"
    if z > 1.81:
        return "🟡 серая зона"
    return "🔴 зона риска"


def _taffler_verdict(z: float) -> str:
    if z > 0.3:
        return "🟢 устойчива"
    if z > 0.2:
        return "🟡 неопределённость"
    return "🔴 риск банкротства"


# ── Sentiment analysis ──────────────────────────────────────────────

POSITIVE_KEYWORDS = [
    "привлекл", "инвестиц", "раунд", "финансирован", "рост",
    "запуст", "выход на рынок", "партнёр", "сотрудничеств",
    "награ", "прем", "грант", "победител", "лучш",
    "экспорт", "масштаб", "выручк", "прибыл", "ipo",
    "патент", "открыт", "расширен", "success",
]

NEGATIVE_KEYWORDS = [
    "банкрот", "ликвидац", "суд ", "иск", "штраф",
    "нарушен", "задолженност", "долг", "убыт", "убыток",
    "увольнен", "сокращен", "претенз", "блокиров",
    "арест", "взыскан", "мошен", "неоплат", "просроч",
]


def _classify_sentiment(title: str, description: str = "") -> str:
    text = (title + " " + description).lower()
    pos_score = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg_score = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    if pos_score > neg_score:
        return "+"
    if neg_score > pos_score:
        return "−"
    return "•"


def _sentiment_icon(sent: str) -> str:
    return {"+" : "📈", "−": "📉", "•": "📰"}.get(sent, "📰")


# ── Block builders ──────────────────────────────────────────────────

def build_block_1_card(
    skolkovo_match: Optional[dict],
    egrul: dict,
    checko: dict,
    inn: str,
    bfo: Optional[dict] = None,
) -> List[str]:
    """Block 1: Company card (facts from EGRUL / Checko / BFO / Skolkovo)."""
    lines: List[str] = []
    lines.append("┃ 📋 <b>КАРТОЧКА КОМПАНИИ</b>")
    bfo = bfo or {}

    name = (
        (skolkovo_match or {}).get("name")
        or checko.get("name")
        or egrul.get("name")
        or bfo.get("name")
        or "Не найдена"
    )
    lines.append(f"┃  Название: <b>{escape_html(name)}</b>")
    lines.append(f"┃  ИНН: {inn}")

    ogrn = checko.get("ogrn") or egrul.get("ogrn", "")
    if ogrn:
        lines.append(f"┃  ОГРН: {ogrn}")

    status = checko.get("status") or egrul.get("status", "")
    if status:
        is_active = "действ" in status.lower()
        icon = "🟢" if is_active else "🔴"
        lines.append(f"┃  Статус: {icon} {escape_html(status)}")

    reg_date = checko.get("registration_date") or egrul.get("registration_date", "")
    if reg_date:
        lines.append(f"┃  Дата регистрации: {reg_date}")

    year_founded = checko.get("year_founded") or (skolkovo_match or {}).get("year_founded")
    if year_founded:
        age = 2026 - int(year_founded)
        lines.append(f"┃  Возраст: {age} лет (с {year_founded})")

    okved = checko.get("okved_name", "")
    if okved:
        lines.append(f"┃  ОКВЭД: {escape_html(okved[:80])}")

    address = checko.get("address", "")
    if address:
        lines.append(f"┃  Адрес: {escape_html(address[:100])}")

    if skolkovo_match:
        lines.append(f"┃  ✅ <b>Участник Сколково</b>")
        cluster = skolkovo_match.get("cluster", "")
        if cluster:
            lines.append(f"┃  Кластер: {escape_html(cluster)}")

    return lines


def build_block_2_financials(financials: dict, source_hint: str = "") -> List[str]:
    """Block 2: Financial statements (raw BFO data, table format). source_hint: 'ФНС' or 'Checko'."""
    if not financials:
        return []

    lines: List[str] = []
    hint = f" ({source_hint})" if source_hint else ""
    lines.append(f"┃ 💰 <b>ФИНАНСОВЫЕ ПОКАЗАТЕЛИ (БФО){hint}</b>")

    years = sorted(financials.keys(), key=lambda x: int(x), reverse=True)[:4]

    header = "┃  <code>Год     Выручка     Прибыль     Активы</code>"
    lines.append(header)

    for year in years:
        yd = financials[year]
        rev = yd.get("revenue", 0)
        profit = yd.get("net_profit", 0)
        assets = yd.get("total_assets", 0)

        rev_s = _fmt_money(rev).rjust(10)
        prof_s = _fmt_money(profit).rjust(10)
        assets_s = _fmt_money(assets).rjust(10)
        lines.append(f"┃  <code>{year}  {rev_s}  {prof_s}  {assets_s}</code>")

    latest = financials[years[0]]
    equity = latest.get("equity", 0)
    cash = latest.get("cash", 0)
    cur_assets = latest.get("current_assets", 0)
    cur_liab = latest.get("current_liabilities", 0)

    lines.append(f"┃  ───────────────────────────────")
    lines.append(f"┃  Собственный капитал: {_fmt_money(equity)}")
    lines.append(f"┃  Денежные средства: {_fmt_money(cash)}")
    lines.append(f"┃  Оборотные активы: {_fmt_money(cur_assets)}")
    lines.append(f"┃  Краткоср. обязательства: {_fmt_money(cur_liab)}")

    return lines


def build_block_3_ratios(financials: dict) -> List[str]:
    """Block 3: Calculated financial ratios with traffic lights."""
    if not financials:
        return []

    from scoring.bfo_ratios import compute_ratios_for_year, compute_dynamic_ratios

    years = sorted(financials.keys(), key=lambda x: int(x))
    latest_year = str(max(int(y) for y in years))
    latest_data = financials[latest_year]

    int_keyed = {}
    for k, v in financials.items():
        try:
            int_keyed[int(k)] = v
        except (ValueError, TypeError):
            int_keyed[k] = v

    static = compute_ratios_for_year(latest_data)
    dynamic = compute_dynamic_ratios(int_keyed)

    lines: List[str] = []
    lines.append(f"┃ 📊 <b>ФИНАНСОВЫЙ АНАЛИЗ ({latest_year})</b>")

    # Liquidity
    cr = static.get("current_ratio", 0)
    qr = static.get("quick_ratio", 0)
    cash_r = static.get("cash_to_current_liab", 0)
    lines.append(f"┃")
    lines.append(f"┃  <b>Ликвидность:</b>")
    lines.append(f"┃  {_traffic_light(cr, 1.0, 2.0)} Текущая: {_fmt_ratio(cr)} (норма ≥2)")
    lines.append(f"┃  {_traffic_light(qr, 0.7, 1.0)} Быстрая: {_fmt_ratio(qr)} (норма ≥1)")
    lines.append(f"┃  {_traffic_light(cash_r, 0.1, 0.2)} Денежная: {_fmt_ratio(cash_r)} (норма ≥0.2)")

    # Solvency
    eq_ratio = static.get("equity_ratio", 0)
    dte = static.get("debt_to_equity", 0)
    leverage = static.get("financial_leverage", 0)
    lines.append(f"┃")
    lines.append(f"┃  <b>Платёжеспособность:</b>")
    lines.append(f"┃  {_traffic_light(eq_ratio, 0.3, 0.5)} Доля собст. капитала: {_fmt_pct(eq_ratio)} (норма ≥50%)")
    lines.append(f"┃  {_traffic_light(dte, 0, 2, inverse=True)} Долг/Капитал: {_fmt_ratio(dte)} (норма ≤1)")
    lines.append(f"┃  {_traffic_light(leverage, 0, 3, inverse=True)} Фин. рычаг: {_fmt_ratio(leverage)} (норма ≤2.5)")

    # Profitability
    gm = static.get("gross_margin", 0)
    om = static.get("operating_margin", 0)
    nm = static.get("net_margin", 0)
    roa = static.get("roa", 0)
    roe = static.get("roe", 0)
    lines.append(f"┃")
    lines.append(f"┃  <b>Рентабельность:</b>")
    lines.append(f"┃  Валовая маржа: {_fmt_pct(gm)}")
    lines.append(f"┃  Операционная маржа: {_fmt_pct(om)}")
    lines.append(f"┃  Чистая маржа: {_fmt_pct(nm)}")
    lines.append(f"┃  {_traffic_light(roa, 0, 0.05)} ROA: {_fmt_pct(roa)}")
    lines.append(f"┃  {_traffic_light(roe, 0, 0.1)} ROE: {_fmt_pct(roe)}")

    # Bankruptcy models
    altman = static.get("altman_z", 0)
    taffler = static.get("taffler_z", 0)
    lines.append(f"┃")
    lines.append(f"┃  <b>Модели банкротства:</b>")
    lines.append(f"┃  Z-Альтмана: {_fmt_ratio(altman)} — {_altman_verdict(altman)}")
    lines.append(f"┃  Z-Таффлера: {_fmt_ratio(taffler)} — {_taffler_verdict(taffler)}")

    # Dynamic
    rev_yoy = dynamic.get("revenue_yoy", 0)
    rev_cagr = dynamic.get("revenue_cagr", 0)
    prof_trend = dynamic.get("profit_trend", 0)
    years_rev = int(dynamic.get("years_with_revenue", 0))
    years_prof = int(dynamic.get("years_profitable", 0))
    years_data = int(dynamic.get("years_of_data", 0))

    lines.append(f"┃")
    lines.append(f"┃  <b>Динамика:</b>")
    yoy_icon = "📈" if rev_yoy > 0 else ("📉" if rev_yoy < 0 else "➡️")
    lines.append(f"┃  {yoy_icon} Рост выручки (YoY): {_fmt_pct(rev_yoy)}")
    if years_data >= 2:
        cagr_icon = "📈" if rev_cagr > 0 else ("📉" if rev_cagr < 0 else "➡️")
        lines.append(f"┃  {cagr_icon} CAGR выручки: {_fmt_pct(rev_cagr)}")
    trend_txt = {1.0: "📈 растёт", -1.0: "📉 падает", 0.0: "➡️ стабильна"}.get(prof_trend, "н/д")
    lines.append(f"┃  Прибыль: {trend_txt}")
    lines.append(f"┃  Лет с выручкой: {years_rev} из {years_data}")
    lines.append(f"┃  Лет прибыльных: {years_prof} из {years_data}")

    # Risk flags
    flags = []
    if static.get("negative_equity", 0):
        flags.append("⚠️ Отрицательный капитал")
    if static.get("overlevered", 0):
        flags.append("⚠️ Чрезмерная долговая нагрузка")
    if static.get("negative_working_capital", 0):
        flags.append("⚠️ Отрицательный оборотный капитал")
    if static.get("zero_revenue", 0):
        flags.append("ℹ️ Нет выручки (pre-revenue стадия)")
    if static.get("loss_making", 0):
        flags.append("ℹ️ Убыточна в последнем году")

    if flags:
        lines.append(f"┃")
        lines.append(f"┃  <b>Флаги риска:</b>")
        for f in flags:
            lines.append(f"┃  {f}")

    return lines


def build_block_4_ml(
    analysis: Optional[dict],
    is_skolkovo: bool = False,
) -> List[str]:
    """Block 4: ML scoring (6 dimensions)."""
    if not analysis:
        return ["┃ 🤖 <b>ML-СКОРИНГ:</b> модели не загружены"]

    lines: List[str] = []
    scores = analysis.get("ml_scores", {})
    overall = analysis.get("ml_overall", 0)
    tl_map = {1: "🔴", 2: "🟡", 3: "🟢"}
    tl = tl_map.get(analysis.get("TrafficLight", 1), "🔴")

    src = "Сколково" if is_skolkovo else "внешние данные"
    lines.append(f"┃ 🤖 <b>ML-СКОРИНГ</b> ({src})")
    lines.append(f"┃")
    lines.append(f"┃  {tl} <b>Общая оценка: {overall:.1f} / 10</b>")
    lines.append(f"┃")

    dims = [
        ("tech_maturity", "🔬", "Технологическая зрелость"),
        ("innovation", "💡", "Инновационность"),
        ("market_potential", "📈", "Рыночный потенциал"),
        ("team_readiness", "👥", "Готовность команды"),
        ("financial_health", "💰", "Финансовое здоровье"),
    ]

    for key, icon, label in dims:
        val = scores.get(key, 0)
        bar_filled = round(val)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        lines.append(f"┃  {icon} {label}")
        lines.append(f"┃     <code>{bar}</code> {val:.1f}")

    # SHAP factors from Comments
    comments = analysis.get("Comments", "")
    if "Ключевые факторы" in comments:
        lines.append(f"┃")
        lines.append(f"┃  <b>Ключевые факторы:</b>")
        for line in comments.split("\n"):
            if line.strip().startswith(("✅", "⚠️")):
                lines.append(f"┃  {line.strip()}")

    return lines


def build_block_5_news(news: dict) -> List[str]:
    """Block 5: News with sentiment."""
    total = news.get("total_count", 0)
    mentions = news.get("mentions", [])
    if total == 0:
        return []

    lines: List[str] = []
    lines.append(f"┃ 📰 <b>УПОМИНАНИЯ В СМИ ({total})</b>")

    for m in mentions[:5]:
        title = m.get("title", "")[:100]
        source = m.get("source", "").upper()
        date = m.get("date", "")[:16]
        sentiment = _classify_sentiment(title)
        icon = _sentiment_icon(sentiment)
        lines.append(f"┃  {icon} [{source}] {escape_html(title)}")
        if date:
            lines.append(f"┃     <i>{date}</i>")

    pos = sum(1 for m in mentions if _classify_sentiment(m.get("title", "")) == "+")
    neg = sum(1 for m in mentions if _classify_sentiment(m.get("title", "")) == "−")
    neu = total - pos - neg
    lines.append(f"┃")
    lines.append(f"┃  Тональность: 📈 {pos} позит. / 📰 {neu} нейтр. / 📉 {neg} негат.")

    return lines


def build_block_6_ai_note(
    has_skolkovo: bool,
    has_financials: bool,
) -> List[str]:
    """Block 6: Note about AI analytics (requires LLM call)."""
    lines: List[str] = []
    lines.append("┃ 🧠 <b>AI-АНАЛИТИКА</b>")

    if has_skolkovo:
        lines.append("┃  TRL/MRL/IRL/CRL — данные из базы Сколково.")
    else:
        lines.append("┃  TRL/MRL/IRL/CRL — <i>нет данных.</i>")
        lines.append("┃  <i>Используйте «Глубокий анализ» для AI-оценки</i>")
        lines.append("┃  <i>технологической зрелости и готовности рынка.</i>")

    if not has_financials:
        lines.append("┃  ℹ️ Финансовая отчётность не найдена.")
        lines.append("┃  Оценка может быть неточной.")

    return lines


def _merge_financials(
    checko_fin: Optional[Dict[str, Any]] = None,
    bfo_fin: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge financials from Checko API and BFO (ФНС). Prefer Checko; fill from BFO. Keys normalized to str."""
    merged: Dict[str, Any] = {}
    for source in (checko_fin or {}, bfo_fin or {}):
        for k, v in source.items():
            key = str(k)
            if key not in merged and isinstance(v, dict) and v:
                merged[key] = v
    return dict(merged)


def build_full_report(
    inn: str,
    company_name: str,
    skolkovo_match: Optional[dict],
    external_data: Dict[str, Any],
    ml_analysis: Optional[dict],
) -> str:
    """Build the complete 6-block analytical report."""
    checko = external_data.get("checko", {})
    egrul = external_data.get("egrul", {})
    bfo = external_data.get("bfo", {})
    news = external_data.get("news", {})
    financials = _merge_financials(checko.get("financials"), bfo.get("financials"))
    financials_source = "Checko" if checko.get("financials") else ("ФНС" if bfo.get("financials") else "")

    display_name = (
        (skolkovo_match or {}).get("name")
        or checko.get("name")
        or egrul.get("name")
        or company_name
        or inn
    )

    parts: List[str] = []

    parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    parts.append(f"🔍 <b>АНАЛИТИЧЕСКИЙ ОТЧЁТ</b>")
    parts.append(f"<b>{escape_html(display_name)}</b>")
    parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Block 1
    block1 = build_block_1_card(skolkovo_match, egrul, checko, inn, bfo=bfo)
    parts.extend(block1)
    parts.append("┠───────────────────────────────")

    # Block 2
    block2 = build_block_2_financials(financials, source_hint=financials_source)
    if block2:
        parts.extend(block2)
        parts.append("┠───────────────────────────────")

    # Block 3
    block3 = build_block_3_ratios(financials)
    if block3:
        parts.extend(block3)
        parts.append("┠───────────────────────────────")

    # Block 4
    block4 = build_block_4_ml(ml_analysis, is_skolkovo=bool(skolkovo_match))
    parts.extend(block4)
    parts.append("┠───────────────────────────────")

    # Block 5
    block5 = build_block_5_news(news)
    if block5:
        parts.extend(block5)
        parts.append("┠───────────────────────────────")

    # Block 6
    block6 = build_block_6_ai_note(
        has_skolkovo=bool(skolkovo_match),
        has_financials=bool(financials),
    )
    parts.extend(block6)
    parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(parts)
