import os
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from analyzer.price_analyzer import analyze_price
from analyzer.hidden_cost_analyzer import analyze_hidden_costs
from analyzer.gotcha_detector import analyze_gotchas
from analyzer.timing_advisor import analyze_timing
from analyzer.review_analyzer import analyze_reviews
from analyzer.live_data import get_auto_dev_listing_models, get_auto_dev_models, get_live_cost_data
from analyzer.nhtsa_reviews import decode_vin
from analyzer.ai_analyzer import run_ai_analysis, run_ai_chat


BASE_DIR = Path(__file__).resolve().parent

load_dotenv()


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(BASE_DIR / "static"),
        static_url_path="",
    )
    CORS(app)

    @app.get("/")
    def index():
        # Serve the single-page app
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/categories")
    def get_categories():
        # App is now specialized for cars only.
        return jsonify({"categories": ["vehicles"]})

    @app.get("/api/nhtsa-decode-vin")
    def nhtsa_decode_vin():
        vin = (request.args.get("vin") or "").strip()
        if not vin or len(vin) < 8:
            return jsonify({"error": "VIN must be at least 8 characters"}), 400
        data = decode_vin(vin)
        if not data.get("make"):
            return jsonify({"error": "Could not decode VIN", "vin": vin}), 404
        return jsonify(data)

    @app.get("/api/vehicle-options")
    def get_vehicle_options():
        make = (request.args.get("make") or "").strip()
        year_raw = (request.args.get("year") or "").strip()
        vehicle_condition = (request.args.get("vehicle_condition") or "used").strip().lower()
        live_only = (request.args.get("live_only") or "").strip().lower() in {"1", "true", "yes"}

        try:
            year = int(year_raw) if year_raw else None
        except ValueError:
            year = None

        if live_only and make and year is not None:
            return jsonify(
                {
                    "make": make,
                    "year": year,
                    "vehicle_condition": vehicle_condition,
                    "models": get_auto_dev_listing_models(make=make, year=year, vehicle_condition=vehicle_condition),
                    "source": "auto_dev_listings",
                }
            )

        return jsonify({"makes_models": get_auto_dev_models(), "source": "auto_dev_models"})

    def _sanitize_analysis_payload(data: Dict[str, Any]) -> Dict[str, Any]:
        # Structured vehicle fields from the UI
        make = (data.get("make") or "").strip()
        model = (data.get("model") or "").strip()
        year_raw = data.get("year")
        product = (data.get("product") or "").strip()
        # App is vehicle-only; ignore any provided category and pin to "vehicles".
        category = "vehicles"
        subcategory = (data.get("subcategory") or "").strip() or None
        context = (data.get("context") or "").strip() or None
        vin = (data.get("vin") or "").strip() or None
        vehicle_condition = (data.get("vehicle_condition") or "used").strip().lower()
        if vehicle_condition not in {"new", "used"}:
            vehicle_condition = "used"

        try:
            year = int(str(year_raw).strip()) if year_raw is not None and str(year_raw).strip() else None
        except (TypeError, ValueError):
            year = None

        if not product:
            product = " ".join(part for part in (make, model, str(year) if year else "") if part)

        try:
            price = float(data.get("price"))
        except (TypeError, ValueError):
            price = None

        years = data.get("years")
        try:
            years = int(years) if years is not None else None
        except (TypeError, ValueError):
            years = None

        # Allowlist overrides to avoid arbitrary keys
        allowed_override_keys = {
            "annual_fuel_cost",
            "annual_charging_cost",
            "insurance_rate_pct",
            "registration",
            "maintenance_pct",
            "maintenance",
            "property_tax_pct",
            "hoi_rate_pct",
            "pmi_pct",
            "phone_plan_monthly",
            "battery_replacement",
            "energy_kwh",
            "water_gallons",
            "major_repair_reserve",
            "custom_down_payment",
            "interest_rate_pct",
            "depreciation_pct",
        }
        raw_overrides = data.get("overrides") or {}
        overrides: Dict[str, Any] = {}
        if isinstance(raw_overrides, dict):
            for key, value in raw_overrides.items():
                if key in allowed_override_keys:
                    overrides[key] = value

        if not product or price is None or not make or not model or year is None:
            raise ValueError("year, make, model, and numeric price are required")

        return {
            "product": product,
            "make": make,
            "model": model,
            "year": year,
            "category": category,
            "subcategory": subcategory,
            "vehicle_condition": vehicle_condition,
            "vin": vin,
            "price": price,
            "years": years,
            "context": context,
            "overrides": overrides,
        }

    @app.post("/api/quick-check")
    def quick_check():
        try:
            payload = _sanitize_analysis_payload(request.get_json(force=True) or {})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        price_result = analyze_price(
            product=payload["product"],
            category=payload["category"],
            price=payload["price"],
            subcategory=payload.get("subcategory"),
            live_prices=(
                get_live_cost_data(
                    product=payload["product"],
                    category=payload["category"],
                    make=payload["make"],
                    model=payload["model"],
                    year=payload["year"],
                    vehicle_condition=payload["vehicle_condition"],
                ).get("retail_prices")
                or []
            ),
        )
        return jsonify({"price_analysis": price_result})

    @app.post("/api/analyze")
    def full_analyze():
        try:
            payload = _sanitize_analysis_payload(request.get_json(force=True) or {})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        live_cost_data = get_live_cost_data(
            product=payload["product"],
            category=payload["category"],
            make=payload["make"],
            model=payload["model"],
            year=payload["year"],
            vehicle_condition=payload["vehicle_condition"],
        )
        print(
            "[Analyze] Live cost data summary:",
            "product=", payload["product"],
            "filters=", {"year": payload["year"], "make": payload["make"], "model": payload["model"], "vehicle_condition": payload["vehicle_condition"]},
            "retail_samples=", len(live_cost_data.get("retail_prices") or []),
            "stats=", live_cost_data.get("retail_price_stats"),
            "query_used=", live_cost_data.get("retail_query_used"),
        )

        price_result = analyze_price(
            product=payload["product"],
            category=payload["category"],
            price=payload["price"],
            subcategory=payload.get("subcategory"),
            live_prices=live_cost_data.get("retail_prices") or [],
        )

        hidden_costs_result = analyze_hidden_costs(
            product=payload["product"],
            category=payload["category"],
            price=payload["price"],
            year=payload["year"],
            years=payload.get("years") or 5,
            overrides=payload.get("overrides") or {},
            live_cost_data=live_cost_data,
            vehicle_condition=payload["vehicle_condition"],
        )

        gotchas_result = analyze_gotchas(
            product=payload["product"],
            category=payload["category"],
            vehicle_condition=payload["vehicle_condition"],
        )

        timing_result = analyze_timing(
            category=payload["category"],
            price=payload["price"],
            live_cost_data=live_cost_data,
        )

        reviews_result = analyze_reviews(
            product=payload["product"],
            category=payload["category"],
            context=payload.get("context"),
            make=payload.get("make"),
            model=payload.get("model"),
            year=payload.get("year"),
            vin=payload.get("vin"),
        )

        return jsonify(
            {
                "input": payload,
                "live_cost_data": live_cost_data,
                "price_analysis": price_result,
                "hidden_costs": hidden_costs_result,
                "gotchas": gotchas_result,
                "timing": timing_result,
                "reviews": reviews_result,
            }
        )

    @app.post("/api/ai-analyze")
    def ai_analyze():
        try:
            data = request.get_json(force=True) or {}
        except Exception:
            data = {}

        input_data = data.get("input") or {}
        make = (input_data.get("make") or "").strip()
        model = (input_data.get("model") or "").strip()
        year_raw = input_data.get("year")
        try:
            year = int(str(year_raw).strip()) if year_raw is not None else None
        except (TypeError, ValueError):
            year = None
        try:
            price = float(input_data.get("price", 0))
        except (TypeError, ValueError):
            price = 0
        if not make or not model or not year or not price:
            return jsonify({"error": "year, make, model, and price are required"}), 400

        analysis = data.get("analysis")
        result = run_ai_analysis(input_data=input_data, analysis=analysis)
        if result.get("error"):
            return jsonify(result), 400
        return jsonify(result)

    @app.post("/api/ai-chat")
    def ai_chat():
        """Multi-turn chat about the vehicle. Requires prior analysis."""
        try:
            data = request.get_json(force=True) or {}
        except Exception:
            data = {}

        input_data = data.get("input") or {}
        make = (input_data.get("make") or "").strip()
        model_name = (input_data.get("model") or "").strip()
        year_raw = input_data.get("year")
        try:
            year = int(str(year_raw).strip()) if year_raw is not None else None
        except (TypeError, ValueError):
            year = None
        user_message = (data.get("user_message") or "").strip()
        messages = data.get("messages") or []

        if not make or not model_name or not year:
            return jsonify({"error": "input (year, make, model) is required"}), 400
        if not user_message:
            return jsonify({"error": "user_message is required"}), 400

        analysis = data.get("analysis")
        result = run_ai_chat(
            input_data=input_data,
            analysis=analysis,
            messages=messages,
            user_message=user_message,
        )
        if result.get("error"):
            return jsonify(result), 400
        return jsonify(result)

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=True)

