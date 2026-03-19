"""
NHTSA API integration for vehicle safety data: recalls, complaints, VIN decode, safety ratings.

APIs used:
- api.nhtsa.gov: complaints, recalls, safety ratings
- vpic.nhtsa.dot.gov: VIN decode (Vehicle Product Information Catalog)
"""
from __future__ import annotations

from typing import Any, Dict, List

import requests


def _safe_get_json(url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    try:
        resp = requests.get(url, params=params or {}, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def decode_vin(vin: str, model_year: int | None = None) -> Dict[str, Any]:
    """
    Decode a 17-character VIN via NHTSA vPIC API.
    Returns make, model, year, body class, etc. Empty dict on failure.
    """
    vin = (vin or "").strip().upper()
    if len(vin) < 8:
        return {}

    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}"
    params: Dict[str, Any] = {"format": "json"}
    if model_year:
        params["modelyear"] = str(model_year)

    raw = _safe_get_json(url, params)
    results = raw.get("Results", [])
    if not results:
        return {}

    r = results[0]
    return {
        "vin": r.get("VIN", vin),
        "make": (r.get("Make") or "").strip() or None,
        "model": (r.get("Model") or "").strip() or None,
        "model_year": r.get("ModelYear") or None,
        "body_class": (r.get("BodyClass") or "").strip() or None,
        "vehicle_type": (r.get("VehicleType") or "").strip() or None,
        "trim": (r.get("Trim") or "").strip() or None,
        "engine_cylinders": r.get("EngineCylinders") or None,
        "displacement_l": r.get("DisplacementL") or None,
        "fuel_type": (r.get("FuelTypePrimary") or "").strip() or None,
        "drive_type": (r.get("DriveType") or "").strip() or None,
        "plant_country": (r.get("PlantCountry") or "").strip() or None,
        "error_code": r.get("ErrorCode"),
        "error_text": (r.get("ErrorText") or "").strip() or None,
    }


def get_safety_ratings(make: str, model: str, model_year: int | None) -> Dict[str, Any]:
    """
    Fetch NCAP safety ratings for a vehicle (make, model, year).
    Returns overall, front crash, side crash ratings if available.
    """
    if not make or not model or not model_year:
        return {}

    url = "https://api.nhtsa.gov/SafetyRatings/modelyear/{}/make/{}/model/{}"
    url = url.format(model_year, make.replace(" ", "%20"), model.replace(" ", "%20"))
    raw = _safe_get_json(url, {"format": "json"})
    results = raw.get("Results", [])
    if not results:
        return {}

    vehicle_id = results[0].get("VehicleId")
    if not vehicle_id:
        return {}

    ratings_url = f"https://api.nhtsa.gov/SafetyRatings/VehicleId/{vehicle_id}"
    ratings_raw = _safe_get_json(ratings_url, {"format": "json"})
    ratings_results = ratings_raw.get("Results", [])
    if not ratings_results:
        return {"vehicle_description": results[0].get("VehicleDescription", "")}

    r = ratings_results[0]
    return {
        "vehicle_description": r.get("VehicleDescription", ""),
        "overall_rating": r.get("OverallRating"),
        "overall_front_crash": r.get("OverallFrontCrashRating"),
        "overall_side_crash": r.get("OverallSideCrashRating"),
        "front_driver": r.get("FrontCrashDriversideRating"),
        "front_passenger": r.get("FrontCrashPassengersideRating"),
        "side_front": r.get("SideCrashFrontSeatRating"),
        "side_rear": r.get("SideCrashRearSeatRating"),
        "rollover": r.get("RolloverRating"),
    }


def get_nhtsa_data(
    make: str,
    model: str,
    model_year: int | None,
    vin: str | None = None,
) -> Dict[str, Any]:
    """
    Fetch recalls, complaints, crash/fire reports, and safety ratings from NHTSA.
    If vin is provided, also decode it and optionally cross-check make/model/year.
    """
    if not make or not model:
        return {"complaints": [], "recalls": [], "crash_or_fire_reports": 0}

    params = {"make": make.upper(), "model": model.upper()}
    if model_year:
        params["modelYear"] = str(model_year)

    complaints_url = "https://api.nhtsa.gov/complaints/complaintsByVehicle"
    recalls_url = "https://api.nhtsa.gov/recalls/recallsByVehicle"

    complaints_raw = _safe_get_json(complaints_url, params=params)
    recalls_raw = _safe_get_json(recalls_url, params=params)

    complaints_by_component: Dict[str, int] = {}
    crash_or_fire = 0
    total_injuries = 0
    total_deaths = 0
    complaints_list: List[Dict[str, Any]] = []

    for c in complaints_raw.get("results", []):
        comp = c.get("components") or c.get("component") or "Unknown"
        complaints_by_component[comp] = complaints_by_component.get(comp, 0) + 1
        if c.get("crash") in (True, "Y") or c.get("fire") in (True, "Y"):
            crash_or_fire += 1
        total_injuries += int(c.get("numberOfInjuries") or 0)
        total_deaths += int(c.get("numberOfDeaths") or 0)
        complaints_list.append(
            {
                "component": comp,
                "summary": c.get("summary", ""),
                "crash": c.get("crash") in (True, "Y"),
                "fire": c.get("fire") in (True, "Y"),
            }
        )

    recalls_list: List[Dict[str, Any]] = []
    for r in recalls_raw.get("results", []):
        recalls_list.append(
            {
                "component": r.get("Component", ""),
                "summary": r.get("Summary", r.get("summary", "")),
                "consequence": r.get("Consequence", ""),
                "remedy": r.get("Remedy", ""),
                "campaign_number": r.get("NHTSACampaignNumber", ""),
            }
        )

    out: Dict[str, Any] = {
        "complaints": complaints_list[:50],
        "complaints_by_component": complaints_by_component,
        "complaint_count": len(complaints_raw.get("results", [])),
        "recalls": recalls_list,
        "recall_count": len(recalls_raw.get("results", [])),
        "crash_or_fire_reports": crash_or_fire,
        "total_injuries": total_injuries,
        "total_deaths": total_deaths,
    }

    safety = get_safety_ratings(make, model, model_year)
    if safety:
        out["safety_ratings"] = safety

    if vin:
        vin_data = decode_vin(vin, model_year)
        if vin_data:
            out["vin_decode"] = vin_data

    return out
