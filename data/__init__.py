from pathlib import Path
import json
from typing import Any, Dict


BASE_DIR = Path(__file__).resolve().parent


def load_json(name: str) -> Dict[str, Any]:
    path = BASE_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_price_ranges() -> Dict[str, Any]:
    return load_json("price_ranges.json")


def load_hidden_costs() -> Dict[str, Any]:
    return load_json("hidden_costs.json")


def load_depreciation() -> Dict[str, Any]:
    return load_json("depreciation.json")


def load_gotchas() -> Dict[str, Any]:
    return load_json("gotchas.json")


def load_timing() -> Dict[str, Any]:
    return load_json("timing.json")


def load_sources() -> Dict[str, Any]:
    return load_json("sources.json")


def load_reviews() -> Dict[str, Any]:
    return load_json("reviews.json")

