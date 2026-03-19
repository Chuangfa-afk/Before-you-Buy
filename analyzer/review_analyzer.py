from __future__ import annotations

from typing import Any, Dict, List, Tuple

from data import load_reviews
from .reddit_reviews import get_reddit_snippets
from .nhtsa_reviews import get_nhtsa_data


def _parse_vehicle_make_model_year(product: str) -> Tuple[str, str, int | None]:
    parts = product.split()
    if len(parts) < 2:
        return "", "", None
    make = parts[0]
    model = " ".join(p for p in parts[1:] if not p.isdigit())
    year = None
    for p in parts:
        if p.isdigit() and len(p) == 4:
            try:
                y = int(p)
                if 1980 <= y <= 2100:
                    year = y
            except ValueError:
                continue
    return make, model, year


def _sentiment_label(score: float) -> str:
    if score >= 4.2:
        return "Very Positive"
    if score >= 3.6:
        return "Mostly Positive"
    if score >= 3.0:
        return "Mixed"
    if score >= 2.0:
        return "Concerning"
    return "Negative"


def analyze_reviews(
    product: str,
    category: str,
    context: str | None = None,
    make: str | None = None,
    model: str | None = None,
    year: int | None = None,
    vin: str | None = None,
) -> Dict[str, Any]:
    kb = load_reviews()
    cat = kb.get(category, {})

    static_pros: List[str] = []
    static_cons: List[str] = []
    base_score = 3.5

    # Use broad subcategory-level pros/cons
    for subcat_data in cat.values():
        static_pros.extend(subcat_data.get("pros", []))
        static_cons.extend(subcat_data.get("cons", []))

    reddit_data = get_reddit_snippets(product, category)
    pos = reddit_data.get("positives", 0)
    neg = reddit_data.get("negatives", 0)

    score = base_score
    score += 0.1 * pos
    score -= 0.1 * neg
    score = max(1.0, min(5.0, score))

    nhtsa_data: Dict[str, Any] = {}
    if category == "vehicles":
        if not make or not model:
            make, model, year_parsed = _parse_vehicle_make_model_year(product)
            if year is None:
                year = year_parsed
        nhtsa_data = get_nhtsa_data(make or "", model or "", year, vin=vin)
        if nhtsa_data.get("crash_or_fire_reports", 0) > 0:
            score -= 0.5

    score = max(1.0, min(5.0, score))

    return {
        "product": product,
        "category": category,
        "score": score,
        "sentiment_label": _sentiment_label(score),
        "static_pros": static_pros,
        "static_cons": static_cons,
        "reddit": reddit_data,
        "nhtsa": nhtsa_data,
    }

