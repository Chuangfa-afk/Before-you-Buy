from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, List

from data import load_price_ranges  # kept for now but no longer used for ranges


_SUBCATEGORY_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    # Vehicles
    "sedan": (
        "camry",
        "civic",
        "accord",
        "corolla",
        "altima",
        "sentra",
        "elantra",
        "sonata",
        "mazda3",
        "mazda6",
        "jetta",
        "passat",
        "impreza",
        "legacy",
        "prius",
        "malibu",
        "fusion",
        "k5",
        "optima",
        "avalon",
        "maxima",
        "focus",
        "dart",
        "versa sedan",
        "mirage g4",
        "ilx",
        "tlx",
    ),
    "suv": (
        "rav4",
        "cr-v",
        "crv",
        "highlander",
        "pilot",
        "4runner",
        "tahoe",
        "suburban",
        "explorer",
        "escape",
        "edge",
        "tucson",
        "santa fe",
        "sorento",
        "telluride",
        "cherokee",
        "grand cherokee",
        "wrangler",
        "bronco",
        "cx-5",
        "cx5",
        "cx-9",
        "cx9",
        "forester",
        "outback",
        "pathfinder",
        "murano",
        "equinox",
        "traverse",
        "blazer",
        "rogue",
        "ascent",
        "palisaide",
        "hyundai kona",
        "hr-v",
        "hrv",
    ),
    "truck": (
        "f-150",
        "f150",
        "silverado",
        "ram 1500",
        "tacoma",
        "tundra",
        "frontier",
        "ranger",
        "colorado",
        "gladiator",
        "titan",
        "ridgeline",
        "maverick",
        "sierra",
        "canyon",
        "ram 2500",
        "ram 3500",
    ),
    "luxury_sedan": (
        "tesla model s",
        "s-class",
        "e-class",
        "5 series",
        "7 series",
    ),
    "compact": (
        "fit",
        "yaris",
        "versa",
        "accent",
        "rio",
        "spark",
        "sonic",
        "fiesta",
        "corolla hatchback",
        "golf",
        "mini",
        "cooper",
        "bolt",
        "impreza hatchback",
        "matrix",
    ),
    "electric": (
        "tesla",
        "model 3",
        "model y",
        "model s",
        "model x",
        "bolt",
        "leaf",
        "mach-e",
        "mustang mach-e",
        "ioniq 5",
        "ev6",
        "id.4",
        "rivian",
        "r1t",
        "r1s",
        "lucid",
        "air",
        "polestar",
    ),
    "hybrid": (
        "prius",
        "hybrid",
        "camry hybrid",
        "rav4 hybrid",
        "cr-v hybrid",
        "accord hybrid",
        "highlander hybrid",
        "escape hybrid",
        "sonata hybrid",
        "ioniq hybrid",
    ),
    "minivan": (
        "sienna",
        "odyssey",
        "pacifica",
        "carnival",
        "grand caravan",
        "voyager",
    ),
}


@dataclass
class PriceVerdict:
    verdict: str
    verdict_icon: str
    verdict_color: str
    percentile_within_range: float


def _auto_detect_subcategory(product: str, category: str) -> Optional[str]:
    """Use keyword mapping to infer a subcategory from the product name."""
    if not product:
        return None
    name = product.lower()

    # Vehicles subcategories
    if category == "vehicles":
        best_match: Optional[tuple[str, int]] = None
        for subcat, keywords in _SUBCATEGORY_KEYWORDS.items():
            if subcat in (
                "sedan",
                "suv",
                "truck",
                "luxury_sedan",
                "compact",
                "electric",
                "hybrid",
                "minivan",
            ):
                matched = [k for k in keywords if k in name]
                if matched:
                    longest = max(len(k) for k in matched)
                    if best_match is None or longest > best_match[1]:
                        best_match = (subcat, longest)
        if best_match is not None:
            return best_match[0]

    return None


def _conservative_fallback_range(
    ranges: Dict[str, Dict[str, float]],
    price: float,
) -> Tuple[str, Dict[str, float]]:
    """
    Conservative fallback when no subcategory is known.

    Instead of picking the closest midpoint (which tends to call everything "Fair"),
    choose the subcategory where the given price looks MOST expensive relative to
    that range: i.e. the highest percentile within [low, high].
    """
    best_key = None
    best_range = None
    best_score = float("-inf")

    for key, r in ranges.items():
        low = float(r.get("low", 0) or 0)
        high = float(r.get("high", low + 1) or (low + 1))
        span = max(high - low, 1.0)
        # Percentile where 0 is at low, 1 is at high, >1 means above high
        pct = (price - low) / span
        if pct > best_score:
            best_score = pct
            best_key = key
            best_range = r

    assert best_key is not None and best_range is not None
    return best_key, best_range


def _determine_verdict(price: float, low: float, mid: float, high: float) -> PriceVerdict:
    span = max(high - low, 1.0)
    percentile = (price - low) / span
    if price <= low:
        return PriceVerdict("Great Deal!", "🟢", "great", max(0.0, percentile))
    if low < price <= mid:
        return PriceVerdict("Fair Price", "🔵", "fair", max(0.0, percentile))
    if mid < price <= high:
        return PriceVerdict("Above Average", "🟡", "above", max(0.0, percentile))
    return PriceVerdict("Overpriced!", "🔴", "overpriced", max(0.0, percentile))


def _ranges_from_live_prices(live_prices: List[float]) -> Optional[Dict[str, float]]:
    if not live_prices:
        return None
    prices = sorted(float(p) for p in live_prices if p is not None)
    if not prices:
        return None
    n = len(prices)

    def q(p: float) -> float:
        if n == 1:
            return prices[0]
        idx = max(0, min(n - 1, int(round(p * (n - 1)))))
        return prices[idx]

    return {
        "low": q(0.2),
        "mid": q(0.5),
        "high": q(0.8),
    }


def analyze_price(
    product: str,
    category: str,
    price: float,
    subcategory: Optional[str] = None,
    live_prices: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """
    Compare user price against *live* market ranges and return a verdict.

    This version intentionally does NOT fall back to static JSON price ranges.
    If live pricing is unavailable, the verdict is marked Unknown.
    """
    category = "vehicles"

    # Auto-detect subcategory (still useful for messaging), but do not use it for ranges.
    auto_subcat = _auto_detect_subcategory(product, category)
    effective_subcat = (subcategory or auto_subcat) or None

    # Build ranges purely from live prices.
    chosen_range: Optional[Dict[str, float]] = None
    if live_prices:
        chosen_range = _ranges_from_live_prices(live_prices) or None

    if not chosen_range:
        return {
            "category": category,
            "subcategory": effective_subcat,
            "used_fallback": False,
            "verdict": "Unknown",
            "verdict_icon": "⚪",
            "verdict_color": "unknown",
            "price": price,
            "ranges": None,
        }

    low = float(chosen_range.get("low", 0) or 0)
    mid = float(chosen_range.get("mid", low) or low)
    high = float(chosen_range.get("high", mid) or mid)

    verdict = _determine_verdict(price, low, mid, high)
    span = max(high - low, 1.0)
    pct_within = (price - low) / span

    return {
        "category": category,
        "subcategory": effective_subcat,
        "used_fallback": False,
        "price": price,
        "ranges": {
            "low": low,
            "mid": mid,
            "high": high,
        },
        "retail_low": low,
        "retail_mid": mid,
        "retail_high": high,
        "percentile_within_range": pct_within,
        "verdict": verdict.verdict,
        "verdict_icon": verdict.verdict_icon,
        "verdict_color": verdict.verdict_color,
    }

