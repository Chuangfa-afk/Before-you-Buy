from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from data import load_timing


MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _median(values: List[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _build_static_timing(category: str, price: float | None = None) -> Dict[str, Any]:
    data = load_timing()
    cat = data.get(category, {})

    now = datetime.utcnow()
    month = now.month

    best_months: List[int] = cat.get("best_months", [])
    worst_months: List[int] = cat.get("worst_months", [])
    save_potential_pct = float(cat.get("save_potential_pct", 0))
    worst_premium_pct = float(cat.get("worst_premium_pct", 3))

    if month in best_months:
        assessment = "Good time to buy"
        score = "good"
    elif month in worst_months:
        assessment = "Challenging time to buy"
        score = "bad"
    else:
        assessment = "Neutral timing"
        score = "neutral"

    events_out = []
    for ev in cat.get("best_events", []):
        ev_month = int(ev.get("month", month))
        month_diff = (ev_month - month) % 12
        days_until = month_diff * 30
        events_out.append(
            {
                "name": ev.get("name", ""),
                "month": ev_month,
                "days_until": days_until,
            }
        )

    # Per-month chart: estimated price and potential savings for each month
    month_chart: List[Dict[str, Any]] = []
    baseline = price if price and price > 0 else 30000.0
    best_price = baseline * (1.0 - save_potential_pct / 100.0)
    worst_price = baseline * (1.0 + worst_premium_pct / 100.0)

    for m in range(1, 13):
        if m in best_months:
            est_price = best_price
            rating = "best"
            savings_pct = save_potential_pct
        elif m in worst_months:
            est_price = worst_price
            rating = "worst"
            savings_pct = -worst_premium_pct
        else:
            # Linear blend between best and worst for neutral months
            est_price = baseline
            rating = "neutral"
            savings_pct = 0.0
        month_chart.append({
            "month": m,
            "month_name": MONTH_NAMES[m - 1],
            "estimated_price": round(est_price, 0),
            "savings_pct": savings_pct,
            "rating": rating,
        })

    # Best month for savings (first best month)
    best_month_for_deal = best_months[0] if best_months else None
    best_estimated_price = round(best_price, 0) if price and price > 0 else None
    potential_savings = round(baseline - best_price, 0) if (price and price > 0 and best_price < baseline) else None

    return {
        "category": category,
        "assessment": assessment,
        "score": score,
        "current_month": month,
        "best_months": best_months,
        "worst_months": worst_months,
        "events": events_out,
        "tips": cat.get("tips", ""),
        "save_potential_pct": save_potential_pct,
        "month_chart": month_chart,
        "best_month_for_deal": best_month_for_deal,
        "best_estimated_price": best_estimated_price,
        "potential_savings": potential_savings,
        "your_quoted_price": round(baseline, 0) if price and price > 0 else None,
        "source": "seasonal_heuristic",
        "confidence_level": "low",
        "confidence_note": "Generic seasonal rule, not specific to this make/model.",
    }


def _parse_created_at(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _build_live_timing(category: str, price: float | None, live_cost_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw_listings = live_cost_data.get("timing_listings") or []
    listing_rows: List[Dict[str, Any]] = []
    for listing in raw_listings:
        created_at = _parse_created_at(listing.get("created_at"))
        try:
            numeric_price = float(listing.get("price"))
        except (TypeError, ValueError):
            continue
        if not created_at or numeric_price <= 0:
            continue
        listing_rows.append(
            {
                "created_at": created_at,
                "month": created_at.month,
                "price": numeric_price,
                "age_days": max((datetime.utcnow() - created_at).days, 0),
            }
        )

    sample_size = len(listing_rows)
    if sample_size < 8:
        return None

    buckets: Dict[int, List[Dict[str, Any]]] = {m: [] for m in range(1, 13)}
    for row in listing_rows:
        buckets[row["month"]].append(row)

    observed_months = [m for m in range(1, 13) if buckets[m]]
    observed_month_count = len(observed_months)
    baseline = float(price) if price and price > 0 else _median([row["price"] for row in listing_rows])

    month_chart: List[Dict[str, Any]] = []
    priced_months: List[Dict[str, Any]] = []
    for month_num in range(1, 13):
        month_rows = buckets[month_num]
        if month_rows:
            est_price = _median([row["price"] for row in month_rows])
            median_age_days = round(_median([float(row["age_days"]) for row in month_rows]))
            listing_count = len(month_rows)
        else:
            est_price = baseline
            median_age_days = None
            listing_count = 0

        month_chart.append(
            {
                "month": month_num,
                "month_name": MONTH_NAMES[month_num - 1],
                "estimated_price": round(est_price, 0),
                "savings_pct": round(((baseline - est_price) / baseline) * 100, 1) if baseline > 0 else 0.0,
                "rating": "neutral",
                "listing_count": listing_count,
                "median_age_days": median_age_days,
            }
        )
        if listing_count:
            priced_months.append(month_chart[-1])

    if not priced_months:
        return None

    comparison_months = [m for m in priced_months if m["listing_count"] >= 2] or priced_months
    best_entry = min(comparison_months, key=lambda item: item["estimated_price"])
    worst_entry = max(comparison_months, key=lambda item: item["estimated_price"])
    best_price = float(best_entry["estimated_price"])
    worst_price = float(worst_entry["estimated_price"])

    for month_data in month_chart:
        if month_data["listing_count"] == 0:
            month_data["rating"] = "neutral"
        elif sample_size >= 15 and month_data["listing_count"] < 2:
            month_data["rating"] = "neutral"
        elif month_data["estimated_price"] <= best_price * 1.01:
            month_data["rating"] = "best"
        elif month_data["estimated_price"] >= worst_price * 0.99:
            month_data["rating"] = "worst"
        else:
            month_data["rating"] = "neutral"

    current_month = datetime.utcnow().month
    current_month_data = month_chart[current_month - 1]
    if current_month_data["listing_count"] >= 2 and current_month_data["estimated_price"] <= baseline * 0.985:
        assessment = "Live listings look favorable now"
        score = "good"
    elif current_month_data["listing_count"] >= 2 and current_month_data["estimated_price"] >= baseline * 1.015:
        assessment = "Current live listings look expensive"
        score = "bad"
    else:
        assessment = "Live timing signal is mixed"
        score = "neutral"

    if sample_size >= 30 and observed_month_count >= 5:
        confidence_level = "high"
    elif sample_size >= 15 and observed_month_count >= 3:
        confidence_level = "medium"
    else:
        confidence_level = "low"

    median_listing_age = round(_median([float(row["age_days"]) for row in listing_rows]))
    events = [
        {"label": f"{sample_size} live listings analyzed"},
        {"label": f"{observed_month_count} listing months observed"},
        {"label": f"Median listing age: {median_listing_age} days"},
    ]

    best_month_for_deal = int(best_entry["month"])
    best_estimated_price = round(best_price, 0)
    potential_savings = round(max(baseline - best_price, 0), 0) if baseline > 0 else None

    return {
        "category": category,
        "assessment": assessment,
        "score": score,
        "current_month": current_month,
        "best_months": [best_month_for_deal],
        "worst_months": [int(worst_entry["month"])],
        "events": events,
        "tips": (
            "Built from current Auto.dev listings for this exact vehicle. "
            "Bars reflect median asking price grouped by listing-created month, so treat this as directional live market signal, not a guaranteed future price."
        ),
        "save_potential_pct": round(((baseline - best_price) / baseline) * 100, 1) if baseline > 0 else 0.0,
        "month_chart": month_chart,
        "best_month_for_deal": best_month_for_deal,
        "best_estimated_price": best_estimated_price,
        "potential_savings": potential_savings,
        "your_quoted_price": round(float(price), 0) if price and price > 0 else round(baseline, 0),
        "source": "live_market",
        "confidence_level": confidence_level,
        "confidence_note": f"Based on {sample_size} live listings spread across {observed_month_count} calendar months.",
    }


def analyze_timing(
    category: str,
    price: float | None = None,
    live_cost_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    live_cost_data = live_cost_data or {}
    live_result = _build_live_timing(category=category, price=price, live_cost_data=live_cost_data)
    if live_result is not None:
        return live_result
    return _build_static_timing(category=category, price=price)

