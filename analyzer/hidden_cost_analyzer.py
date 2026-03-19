from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from data import load_hidden_costs, load_depreciation, load_sources
from .price_analyzer import _auto_detect_subcategory


@dataclass
class CostItem:
    name: str
    amount: float
    annual_amount: float
    confidence: str
    source: str
    source_url: str
    source_note: str
    source_year: int
    is_live: bool = False
    is_override: bool = False
    is_appreciation: bool = False
    key: str = ""
    basis: str = ""


_INSURANCE_RATE_PCT_BY_SUBCATEGORY = {
    "compact": 3.2,
    "sedan": 3.5,
    "hybrid": 3.6,
    "minivan": 3.7,
    "suv": 3.9,
    "truck": 4.1,
    "electric": 4.3,
    "luxury_sedan": 5.2,
}

_MAINTENANCE_BASE_BY_SUBCATEGORY = {
    "compact": 650,
    "sedan": 775,
    "hybrid": 825,
    "minivan": 900,
    "suv": 950,
    "truck": 1050,
    "electric": 550,
    "luxury_sedan": 1450,
}


def _get_source_meta(category: str, key: str) -> Dict[str, Any]:
    sources = load_sources()
    cat = sources.get(category, {})
    source_key = {
        "annual_fuel_cost": "fuel",
        "annual_charging_cost": "charging",
        "insurance_rate_pct": "insurance",
        "maintenance": "maintenance",
        "depreciation_pct": "depreciation",
    }.get(key, key)
    meta = cat.get(source_key, {})
    return {
        "source": meta.get("source", "Unknown"),
        "source_url": meta.get("url", ""),
        "source_year": int(meta.get("year", 2024)),
        "source_note": meta.get("note", ""),
        "confidence": meta.get("confidence", "medium"),
    }


def _get_depreciation_pct(category: str, subcat: Optional[str]) -> float:
    """
    Returns an ANNUAL depreciation percentage (positive for loss in value).

    For real estate, check for typical_annual_appreciation_pct and return
    a NEGATIVE value to model appreciation instead of depreciation.
    """
    dep = load_depreciation()
    cat = dep.get(category, {})

    if subcat and subcat in cat:
        return float(cat[subcat].get("annual_pct", cat.get("default_annual_pct", 10)))

    return float(cat.get("default_annual_pct", 10))


def _median(values: List[float]) -> Optional[float]:
    cleaned = sorted(float(v) for v in values if v is not None)
    if not cleaned:
        return None
    mid = len(cleaned) // 2
    if len(cleaned) % 2:
        return cleaned[mid]
    return (cleaned[mid - 1] + cleaned[mid]) / 2.0


def _vehicle_age(year: Optional[int]) -> Optional[int]:
    if not year:
        return None
    return max(datetime.utcnow().year - year, 0)


def _insurance_rate_pct(subcat: Optional[str], price: float, age: Optional[int]) -> tuple[float, str]:
    rate = float(_INSURANCE_RATE_PCT_BY_SUBCATEGORY.get(subcat or "", 3.8))
    price_band = "under $20k"
    if price >= 80000:
        rate += 1.0
        price_band = "$80k+"
    elif price >= 55000:
        rate += 0.6
        price_band = "$55k-$80k"
    elif price >= 35000:
        rate += 0.3
        price_band = "$35k-$55k"
    elif price >= 20000:
        price_band = "$20k-$35k"

    if age is not None:
        if age <= 2:
            rate += 0.2
        elif age >= 8:
            rate -= 0.3

    age_note = f"{age}-year-old vehicle" if age is not None else "typical model-year age"
    return rate, f"{subcat or 'vehicle'} insurance profile, {price_band} value band, {age_note}"


def _registration_amount(subcat: Optional[str], price: float, age: Optional[int]) -> tuple[float, str]:
    if price >= 80000:
        annual = 725.0
        price_band = "$80k+"
    elif price >= 55000:
        annual = 575.0
        price_band = "$55k-$80k"
    elif price >= 35000:
        annual = 450.0
        price_band = "$35k-$55k"
    elif price >= 20000:
        annual = 325.0
        price_band = "$20k-$35k"
    else:
        annual = 250.0
        price_band = "under $20k"

    if subcat == "electric":
        annual += 120.0
    elif subcat == "truck":
        annual += 60.0
    elif subcat == "luxury_sedan":
        annual += 90.0

    if age is not None and age <= 2:
        annual += 40.0

    return annual, f"{subcat or 'vehicle'} registration profile, {price_band} value band"


def _maintenance_amount(
    subcat: Optional[str],
    age: Optional[int],
    median_listing_miles: Optional[float],
) -> tuple[float, str]:
    annual = float(_MAINTENANCE_BASE_BY_SUBCATEGORY.get(subcat or "", 850))
    age_note = "typical age"
    if age is not None:
        age_note = f"{age}-year-old vehicle"
        if age <= 2:
            annual *= 0.9
        elif age >= 8:
            annual *= 1.35
        elif age >= 5:
            annual *= 1.15

    miles_note = "mileage unavailable"
    if median_listing_miles is not None:
        miles_note = f"median market mileage {int(round(median_listing_miles)):,}"
        if median_listing_miles >= 120000:
            annual *= 1.45
        elif median_listing_miles >= 80000:
            annual *= 1.2
        elif median_listing_miles <= 25000:
            annual *= 0.92

    return annual, f"{subcat or 'vehicle'} maintenance profile, {age_note}, {miles_note}"


def _annualize_costs(
    category: str,
    subcat: Optional[str],
    price: float,
    year: Optional[int],
    years: int,
    overrides: Dict[str, Any],
    live_cost_data: Dict[str, Any],
    vehicle_condition: str,
) -> tuple[List[CostItem], Dict[str, float]]:
    cfg = load_hidden_costs().get(category, {})
    items: List[CostItem] = []
    editable_defaults: Dict[str, float] = {}
    age = _vehicle_age(year)
    vehicle_condition = (vehicle_condition or "used").strip().lower()
    timing_listings = live_cost_data.get("timing_listings") or []
    market_miles = _median(
        [
            float(listing.get("miles"))
            for listing in timing_listings
            if listing.get("miles") is not None
        ]
    )

    def add_item(
        key: str,
        name: str,
        annual_amount: float,
        basis: str,
        is_live: bool = False,
    ):
        meta = _get_source_meta(category, key)
        override_val = overrides.get(key)
        amount = float(override_val if override_val is not None else annual_amount)
        editable_defaults[key] = round(float(amount), 2)
        items.append(
            CostItem(
                name=name,
                amount=amount * years,
                annual_amount=amount,
                is_live=is_live,
                is_override=override_val is not None,
                is_appreciation=False,
                key=key,
                basis=basis,
                **meta,
            )
        )

    if category == "vehicles":
        # Fuel or Charge fee (for electric)
        is_electric = subcat == "electric"
        if is_electric:
            charge_cfg = cfg.get("charging", {})
            annual_charge_default = float(charge_cfg.get("annual_charging_cost", 600))
            live_charge = live_cost_data.get("annual_fuel_cost")  # EPA reports electricity cost as fuelCost08 for EVs
            annual_amount = float(live_charge if live_charge is not None else annual_charge_default)
            override_val = overrides.get("annual_charging_cost")
            amount = float(override_val if override_val is not None else annual_amount)
            meta = _get_source_meta(category, "charging")
            items.append(
                CostItem(
                    name="Charge fee",
                    amount=amount * years,
                    annual_amount=amount,
                    is_live=bool(live_charge),
                    is_override=override_val is not None,
                    is_appreciation=False,
                    key="annual_charging_cost",
                    basis="EPA annual electricity cost for this model" if live_charge is not None else "Fallback EV charging estimate",
                    **meta,
                )
            )
            editable_defaults["annual_charging_cost"] = round(float(amount), 2)
        else:
            fuel_cfg = cfg.get("fuel", {})
            annual_fuel_default = float(fuel_cfg.get("annual_fuel_cost", 1500))
            live_fuel = live_cost_data.get("annual_fuel_cost")
            annual_amount = float(live_fuel or annual_fuel_default)
            override_val = overrides.get("annual_fuel_cost")
            amount = float(override_val if override_val is not None else annual_amount)
            meta = _get_source_meta(category, "fuel")
            items.append(
                CostItem(
                    name="Fuel",
                    amount=amount * years,
                    annual_amount=amount,
                    is_live=bool(live_fuel),
                    is_override=override_val is not None,
                    is_appreciation=False,
                    key="annual_fuel_cost",
                    basis="EPA annual fuel cost for this model" if live_fuel is not None else "Fallback fuel-cost estimate",
                    **meta,
                )
            )
            editable_defaults["annual_fuel_cost"] = round(float(amount), 2)

        insurance_rate_pct, insurance_basis = _insurance_rate_pct(subcat, price, age)
        insurance_override = overrides.get("insurance_rate_pct")
        applied_insurance_rate_pct = float(
            insurance_override if insurance_override is not None else insurance_rate_pct
        )
        annual_insurance = price * (applied_insurance_rate_pct / 100.0)
        editable_defaults["insurance_rate_pct"] = round(applied_insurance_rate_pct, 2)
        insurance_meta = _get_source_meta(category, "insurance_rate_pct")
        items.append(
            CostItem(
                name="Insurance",
                amount=annual_insurance * years,
                annual_amount=annual_insurance,
                is_live=False,
                is_override=insurance_override is not None,
                is_appreciation=False,
                key="insurance_rate_pct",
                basis=f"{applied_insurance_rate_pct:.1f}% of value based on {insurance_basis}",
                **insurance_meta,
            )
        )

        registration, registration_basis = _registration_amount(subcat, price, age)
        add_item("registration", "Registration", registration, registration_basis)

        maintenance, maintenance_basis = _maintenance_amount(subcat, age, market_miles)
        if vehicle_condition == "used":
            maintenance *= 1.12
            maintenance_basis += ", used-vehicle uplift"
        else:
            maintenance *= 0.94
            maintenance_basis += ", new-vehicle discount"
        add_item("maintenance", "Maintenance & Repairs", maintenance, maintenance_basis)

    return items, editable_defaults


def analyze_hidden_costs(
    product: str,
    category: str,
    price: float,
    year: Optional[int],
    years: int,
    overrides: Dict[str, Any],
    live_cost_data: Optional[Dict[str, Any]] = None,
    subcategory: Optional[str] = None,
    vehicle_condition: str = "used",
) -> Dict[str, Any]:
    live_cost_data = live_cost_data or {}
    effective_subcategory = subcategory or _auto_detect_subcategory(product, category)

    cost_items, editable_defaults = _annualize_costs(
        category=category,
        subcat=effective_subcategory,
        price=price,
        year=year,
        years=years,
        overrides=overrides,
        live_cost_data=live_cost_data,
        vehicle_condition=vehicle_condition,
    )

    total_hidden_costs = sum(ci.amount for ci in cost_items)

    # Depreciation (or appreciation for real estate)
    dep_override = overrides.get("depreciation_pct")
    annual_dep_pct = float(
        dep_override if dep_override is not None else _get_depreciation_pct(category, effective_subcategory)
    )
    if dep_override is None:
        if vehicle_condition == "used":
            annual_dep_pct = max(annual_dep_pct - 4.0, 8.0)
        else:
            annual_dep_pct = annual_dep_pct + 1.5
    value = price
    yearly_breakdown = []
    for year in range(1, years + 1):
        value *= 1.0 - (annual_dep_pct / 100.0)
        yearly_breakdown.append(
            {
                "year": year,
                "estimated_value": value,
                "annual_depreciation_pct": annual_dep_pct,
            }
        )

    value_after_years = value
    total_cost_of_ownership = price + total_hidden_costs - max(
        value_after_years, 0.0
    )
    true_cost = total_cost_of_ownership

    # If true_cost is negative, this is a net gain (e.g., appreciating asset)
    summary_label = "True Cost of Ownership"
    summary_style = "default"
    if true_cost < 0:
        summary_label = f"Net Gain Over {years} Years"
        summary_style = "net_gain"

    return {
        "purchase_price": price,
        "total_hidden_costs": total_hidden_costs,
        "total_cost_of_ownership": total_cost_of_ownership,
        "value_after_years": value_after_years,
        "true_cost": true_cost,
        "summary_label": summary_label,
        "summary_style": summary_style,
        "cost_items": [asdict(ci) for ci in cost_items],
        "yearly_breakdown": yearly_breakdown,
        "editable_defaults": editable_defaults | {"depreciation_pct": round(annual_dep_pct, 2)},
    }

