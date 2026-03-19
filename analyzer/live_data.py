from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Tuple
import requests


EPA_BASE = "https://fueleconomy.gov/ws/rest"
AUTO_DEV_MODELS_URL = "https://api.auto.dev/api/models"
AUTO_DEV_LISTINGS_URL = "https://api.auto.dev/listings"
_AUTO_DEV_MODELS_CACHE: Dict[str, List[str]] | None = None
_AUTO_DEV_LISTING_MODELS_CACHE: Dict[Tuple[int, str], List[str]] = {}


def _parse_vehicle_make_model_year(product: str) -> Tuple[str, str, int | None]:
    parts = product.split()
    if len(parts) < 2:
        return "", "", None
    make = parts[0]
    model_parts: List[str] = []
    year: int | None = None
    for p in parts[1:]:
        if p.isdigit() and len(p) == 4:
            try:
                y = int(p)
                if 1980 <= y <= 2100:
                    year = y
                    continue
            except ValueError:
                pass
        model_parts.append(p)
    model = " ".join(model_parts).strip()
    return make, model, year


def _fetch_epa_fuel_prices() -> Dict[str, float]:
    """Fetch current fuel prices from EPA (free, no key). Returns dict with regular, diesel, electric, etc."""
    out: Dict[str, float] = {}
    try:
        r = requests.get(f"{EPA_BASE}/fuelprices", timeout=5)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for tag in ("regular", "premium", "diesel", "electric", "midgrade", "e85", "cng", "lpg"):
            el = root.find(tag)
            if el is not None and el.text:
                try:
                    out[tag] = float(el.text)
                except ValueError:
                    pass
    except Exception:
        pass
    return out


def _fetch_epa_vehicle_id(year: int, make: str, model: str) -> str | None:
    """Get first EPA vehicle ID for year/make/model. Tries full model then base model (first word)."""
    for model_val in (model, model.split()[0] if model else ""):
        if not model_val:
            continue
        try:
            url = f"{EPA_BASE}/vehicle/menu/options"
            params = {"year": year, "make": make, "model": model_val}
            r = requests.get(url, params=params, timeout=5)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            item = root.find(".//menuItem/value")
            if item is not None and item.text:
                return item.text.strip()
        except Exception:
            continue
    return None


def _fetch_epa_vehicle(vehicle_id: str) -> Dict[str, Any]:
    """Get EPA vehicle record (fuel cost, MPG). Returns dict with annual_fuel_cost, combined_mpg, etc."""
    out: Dict[str, Any] = {}
    try:
        r = requests.get(f"{EPA_BASE}/vehicle/{vehicle_id}", timeout=5)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for tag, key in (("fuelCost08", "annual_fuel_cost"), ("comb08", "combined_mpg"), ("city08", "city_mpg"), ("highway08", "highway_mpg")):
            el = root.find(tag)
            if el is not None and el.text:
                try:
                    out[key] = int(float(el.text)) if key == "annual_fuel_cost" else float(el.text)
                except ValueError:
                    pass
    except Exception:
        pass
    return out


def get_auto_dev_models() -> Dict[str, List[str]]:
    global _AUTO_DEV_MODELS_CACHE
    if _AUTO_DEV_MODELS_CACHE is not None:
        return _AUTO_DEV_MODELS_CACHE

    api_key = os.getenv("AUTO_DEV_API_KEY")
    if not api_key:
        return {}

    try:
        resp = requests.get(
            AUTO_DEV_MODELS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            _AUTO_DEV_MODELS_CACHE = {
                str(make): sorted(
                    [
                        str(model)
                        for model in models
                        if isinstance(model, str) and model.strip()
                    ]
                )
                for make, models in data.items()
                if isinstance(make, str) and isinstance(models, list)
            }
            return _AUTO_DEV_MODELS_CACHE
    except Exception as e:
        print("[Auto.dev] ERROR loading make/model catalog:", repr(e))

    return {}


def get_auto_dev_listing_models(
    make: str,
    year: int,
    vehicle_condition: str = "used",
    max_pages: int = 8,
) -> List[str]:
    make = (make or "").strip()
    if not make or not year:
        return []

    vehicle_condition = (vehicle_condition or "used").strip().lower()
    if vehicle_condition not in {"new", "used"}:
        vehicle_condition = "used"

    cache_key = (year, make.casefold(), vehicle_condition)
    cached = _AUTO_DEV_LISTING_MODELS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    api_key = os.getenv("AUTO_DEV_API_KEY")
    if not api_key:
        return []

    models: set[str] = set()
    page = 1
    limit = 100

    try:
        while page <= max_pages:
            js = _run_auto_dev_listing_query(
                api_key,
                {
                    "limit": limit,
                    "page": page,
                    "vehicle.year": year,
                    "vehicle.make": make,
                    "retailListing.used": "true" if vehicle_condition == "used" else "false",
                },
            )
            listings = js.get("data", []) or []
            if not listings:
                break

            for listing in listings:
                vehicle = listing.get("vehicle") or {}
                retail_listing = listing.get("retailListing") or {}
                model = (vehicle.get("model") or "").strip()
                price = retail_listing.get("price")
                try:
                    numeric_price = float(price)
                except (TypeError, ValueError):
                    numeric_price = 0
                if model and numeric_price > 0:
                    models.add(model)

            if len(listings) < limit:
                break
            page += 1
    except Exception as e:
        print("[Auto.dev] ERROR loading year/make listing models:", repr(e))
        return []

    out = sorted(models)
    _AUTO_DEV_LISTING_MODELS_CACHE[cache_key] = out
    return out


def _collect_listing_prices(listings: List[Dict[str, Any]]) -> List[float]:
    prices: List[float] = []
    for listing in listings:
        rl = listing.get("retailListing") or {}
        price = rl.get("price")
        try:
            numeric_price = float(price)
            if numeric_price > 0:
                prices.append(numeric_price)
        except (TypeError, ValueError):
            continue
    return prices


def _collect_timing_listings(listings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for listing in listings:
        retail_listing = listing.get("retailListing") or {}
        vehicle = listing.get("vehicle") or {}
        price = retail_listing.get("price")
        try:
            numeric_price = float(price)
        except (TypeError, ValueError):
            continue
        if numeric_price <= 0:
            continue

        out.append(
            {
                "created_at": listing.get("createdAt"),
                "price": numeric_price,
                "miles": retail_listing.get("miles"),
                "dealer": retail_listing.get("dealer"),
                "used": retail_listing.get("used"),
                "trim": vehicle.get("trim"),
            }
        )
    return out


def _run_auto_dev_listing_query(api_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
    print("[Auto.dev] Requesting listings with params:", params)
    resp = requests.get(
        AUTO_DEV_LISTINGS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        params=params,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_live_cost_data(
    product: str,
    category: str,
    make: str | None = None,
    model: str | None = None,
    year: int | None = None,
    vehicle_condition: str = "used",
) -> Dict[str, Any]:
    """
    Fetches best-effort live cost data.

    For cars, this can include live retail listing prices from Auto.dev if an
    AUTO_DEV_API_KEY is configured. All failures fall back silently to static
    ranges so the app remains usable without the key.
    """
    data: Dict[str, Any] = {}

    if category == "vehicles":
        parsed_make, parsed_model, parsed_year = _parse_vehicle_make_model_year(product)
        make = (make or parsed_make or "").strip()
        model = (model or parsed_model or "").strip()
        year = year if year is not None else parsed_year
        vehicle_condition = (vehicle_condition or "used").strip().lower()
        if vehicle_condition not in {"new", "used"}:
            vehicle_condition = "used"

        # Auto.dev: live retail listing prices (requires API key)
        api_key = os.getenv("AUTO_DEV_API_KEY")
        if api_key and product:
            try:
                query_attempts: List[Tuple[str, Dict[str, Any]]] = []
                if year and make and model:
                    query_attempts.append(
                        (
                            "exact_year_make_model",
                            {
                                "limit": 50,
                                "vehicle.year": year,
                                "vehicle.make": make,
                                "vehicle.model": model,
                                "retailListing.used": "true" if vehicle_condition == "used" else "false",
                            },
                        )
                    )
                if make and model:
                    query_attempts.append(
                        (
                            "make_model_any_year",
                            {
                                "limit": 50,
                                "vehicle.make": make,
                                "vehicle.model": model,
                                "retailListing.used": "true" if vehicle_condition == "used" else "false",
                            },
                        )
                    )

                for query_name, params in query_attempts:
                    js = _run_auto_dev_listing_query(api_key, params)
                    listings = js.get("data", []) or []
                    print("[Auto.dev] Query", query_name, "got", len(listings), "results")
                    prices = _collect_listing_prices(listings)
                    if not prices:
                        print("[Auto.dev] No usable prices returned for params:", params)
                        continue

                    prices.sort()
                    n = len(prices)

                    def q(p: float) -> float:
                        if n == 1:
                            return prices[0]
                        idx = max(0, min(n - 1, int(round(p * (n - 1)))))
                        return prices[idx]

                    data["retail_prices"] = prices
                    data["retail_price_stats"] = {
                        "low": q(0.2),
                        "mid": q(0.5),
                        "high": q(0.8),
                        "sample_size": n,
                    }
                    data["timing_listings"] = _collect_timing_listings(listings)
                    data["retail_query_used"] = query_name
                    data["vehicle_condition"] = vehicle_condition
                    print("[Auto.dev] Using", n, "prices. Low/mid/high:", data["retail_price_stats"])
                    break
            except Exception as e:
                # Log the error so we can debug why live data failed.
                print("[Auto.dev] ERROR while fetching listings:", repr(e))

        # EPA fuel economy (free, no key): real MPG and annual fuel cost for this vehicle
        if make and model and year:
            vid = _fetch_epa_vehicle_id(year, make, model)
            if vid:
                epa_vehicle = _fetch_epa_vehicle(vid)
                if epa_vehicle.get("annual_fuel_cost") is not None:
                    data["annual_fuel_cost"] = epa_vehicle["annual_fuel_cost"]
                    data["epa_vehicle"] = epa_vehicle
        # EPA current fuel prices (free) for reference / future custom calc
        fuel_prices = _fetch_epa_fuel_prices()
        if fuel_prices:
            data["fuel_prices"] = fuel_prices

    return data

