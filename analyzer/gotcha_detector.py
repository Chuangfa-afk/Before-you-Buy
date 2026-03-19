from __future__ import annotations

from typing import Any, Dict, List

from data import load_gotchas


def analyze_gotchas(product: str, category: str, vehicle_condition: str = "used") -> Dict[str, Any]:
    data = load_gotchas()
    cat_gotchas: List[Dict[str, Any]] = data.get(category, [])

    by_severity: Dict[str, List[Dict[str, Any]]] = {
        "high": [],
        "medium": [],
        "low": [],
    }
    negotiable_count = 0

    for g in cat_gotchas:
        condition = (g.get("condition") or "both").strip().lower()
        if condition not in {"both", vehicle_condition}:
            continue
        sev = g.get("severity", "medium")
        if sev not in by_severity:
            by_severity[sev] = []
        by_severity[sev].append(g)
        if g.get("negotiable"):
            negotiable_count += 1

    tips = data.get("tips", {}).get(category, "")
    negotiation_tips = data.get("negotiation_tips", [])

    return {
        "category": category,
        "product": product,
        "vehicle_condition": vehicle_condition,
        "by_severity": by_severity,
        "negotiable_count": negotiable_count,
        "negotiable_any": negotiable_count > 0,
        "tips": tips,
        "negotiation_tips": negotiation_tips,
    }

