"""
AI-powered analysis of the selected vehicle using an LLM.
Supports Groq, Google Gemini, OpenAI API, and OpenAI-compatible endpoints.
Falls back to static knowledge-base synthesis when API is unavailable (demo mode).
"""
from __future__ import annotations

import os
import time
import random
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

# Rate limit retry config
GROQ_RATE_LIMIT_MAX_RETRIES = int(os.getenv("GROQ_RATE_LIMIT_MAX_RETRIES", "3"))
GROQ_RATE_LIMIT_BASE_DELAY = float(os.getenv("GROQ_RATE_LIMIT_BASE_DELAY", "5"))
GROQ_RATE_LIMIT_MAX_DELAY = float(os.getenv("GROQ_RATE_LIMIT_MAX_DELAY", "60"))


def _infer_subcategory(product: str) -> Optional[str]:
    """Infer vehicle subcategory from product name for relevant pros/cons."""
    try:
        from .price_analyzer import _auto_detect_subcategory
        return _auto_detect_subcategory(product or "", "vehicles")
    except Exception:
        return None


def _build_static_analysis(input_data: Dict[str, Any], analysis: Optional[Dict[str, Any]]) -> str:
    """
    Generate an enriched analysis from static knowledge when no LLM API is available.
    Synthesizes input, analysis data, and knowledge base into a detailed, actionable summary.
    """
    year = input_data.get("year", "N/A")
    make = input_data.get("make", "N/A")
    model = input_data.get("model", "N/A")
    product = f"{year} {make} {model}".strip()
    condition = (input_data.get("vehicle_condition") or "used").capitalize()
    price = float(input_data.get("price", 0))
    years = int(input_data.get("years") or 5)
    subcat = _infer_subcategory(product)

    lines: List[str] = [
        f"{year} {make} {model} — {condition} at ${price:,.0f}",
        "",
        "━━━ PRICE & MARKET VALUE ━━━",
        "",
    ]

    if analysis:
        pa = analysis.get("price_analysis") or {}
        verdict = pa.get("verdict")
        ranges = pa.get("ranges") or {}
        if verdict and verdict != "Unknown":
            low = ranges.get("low", 0)
            mid = ranges.get("mid", low)
            high = ranges.get("high", mid)
            lines.append(f"Market verdict: {verdict}")
            lines.append(f"Typical range: ${low:,.0f} (low) — ${mid:,.0f} (mid) — ${high:,.0f} (high)")
            if price < low:
                lines.append("Your quote is below typical low — strong negotiating position.")
            elif price > high:
                lines.append("Your quote is above typical high — consider negotiating or shopping around.")
            else:
                lines.append("Your quote sits within the typical market range.")
        else:
            lines.append(f"Your quoted price of ${price:,.0f} is the starting point. Run the full analysis for live market comparison.")
    else:
        lines.append(f"Your quoted price: ${price:,.0f}. Run the full analysis above for live market data and verdict.")

    lines.extend(["", "━━━ TRUE COST OF OWNERSHIP ━━━", ""])

    if analysis:
        hc = analysis.get("hidden_costs") or {}
        total = hc.get("total_true_cost")
        cost_items = hc.get("cost_items") or []
        if total is not None:
            lines.append(f"Over {years} years, total cost ≈ ${total:,.0f} (purchase + running costs − resale)")
            if cost_items:
                lines.append("")
                for item in sorted(cost_items, key=lambda x: abs(x.get("amount", 0)), reverse=True)[:6]:
                    name = item.get("name", "")
                    amt = item.get("amount", 0)
                    if name and amt:
                        lines.append(f"  • {name}: ${amt:,.0f}")
        else:
            lines.append("Run the full analysis for a detailed cost breakdown (fuel, insurance, maintenance, depreciation).")
    else:
        lines.append("Run the full analysis for fuel, insurance, maintenance, registration, and depreciation estimates.")

    lines.extend(["", "━━━ TIMING & NEGOTIATION ━━━", ""])

    if analysis:
        timing = analysis.get("timing") or {}
        assessment = timing.get("assessment")
        best_month = timing.get("best_month_for_deal")
        savings = timing.get("potential_savings")
        if assessment:
            lines.append(assessment)
        if best_month:
            month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            mn = month_names[best_month] if 1 <= best_month <= 12 else str(best_month)
            lines.append(f"Historically stronger pricing: {mn}")
        if savings and savings > 0:
            lines.append(f"Potential savings vs. peak: ~${savings:,.0f}")
        if not (assessment or best_month):
            lines.append("Consider seasonal trends — end-of-month and year-end often see better deals.")
    else:
        lines.append("End-of-month and year-end often see better dealer incentives. Run analysis for vehicle-specific timing.")

    lines.extend(["", "━━━ OWNER SENTIMENT & PROS/CONS ━━━", ""])

    reviews_data: Dict[str, Any] = {}
    try:
        from data import load_reviews
        reviews_data = load_reviews().get("vehicles", {})
    except Exception:
        pass

    if analysis:
        reviews = analysis.get("reviews") or {}
        score = reviews.get("score")
        label = reviews.get("sentiment_label", "")
        if score is not None:
            lines.append(f"Sentiment: {score:.1f}/5 ({label})")
        static_pros = reviews.get("static_pros") or []
        static_cons = reviews.get("static_cons") or []
        if static_pros:
            lines.append("Pros: " + "; ".join(static_pros[:3]))
        if static_cons:
            lines.append("Cons: " + "; ".join(static_cons[:3]))
    if subcat and subcat in reviews_data and not (analysis and (analysis.get("reviews") or {}).get("static_pros")):
        sub = reviews_data.get(subcat, {})
        pros = sub.get("pros", [])[:2]
        cons = sub.get("cons", [])[:2]
        if pros:
            lines.append("Typical pros: " + "; ".join(pros))
        if cons:
            lines.append("Typical cons: " + "; ".join(cons))

    if not (analysis and (analysis.get("reviews") or {}).get("score") is not None) and not subcat:
        lines.append("Check Reddit and owner forums for real-world feedback on this model.")

    lines.extend(["", "━━━ GOTCHAS & JUNK FEES ━━━", ""])

    gotchas_data: List[Dict[str, Any]] = []
    try:
        from data import load_gotchas
        all_g = load_gotchas().get("vehicles", [])
        cond = condition.lower()
        for g in all_g:
            c = (g.get("condition") or "both").strip().lower()
            if c in ("both", cond):
                gotchas_data.append(g)
    except Exception:
        pass

    if analysis:
        gotchas = analysis.get("gotchas") or {}
        by_sev = gotchas.get("by_severity") or {}
        high_g = by_sev.get("high", [])
        med_g = by_sev.get("medium", [])
        for g in (high_g + med_g)[:5]:
            name = g.get("name", "")
            cost = g.get("typical_cost", 0)
            neg = " (negotiable)" if g.get("negotiable") else ""
            if name:
                lines.append(f"  • {name}: ~${cost:,.0f}{neg}")
        tips = gotchas.get("tips", "")
        if tips:
            lines.append("")
            lines.append(f"Tip: {tips[:200]}{'…' if len(tips) > 200 else ''}")
    elif gotchas_data:
        for g in gotchas_data[:5]:
            name = g.get("name", "")
            cost = g.get("typical_cost", 0)
            if name:
                lines.append(f"  • {name}: ~${cost:,.0f}")
        try:
            from data import load_gotchas
            tips = load_gotchas().get("tips", {}).get("vehicles", "")
            if tips:
                lines.append("")
                lines.append(f"Tip: {tips[:180]}…")
        except Exception:
            pass

    lines.extend(["", "━━━ SAFETY (NHTSA) ━━━", ""])

    if analysis:
        nhtsa = (analysis.get("reviews") or {}).get("nhtsa") or {}
        rc = nhtsa.get("recall_count", 0)
        cc = nhtsa.get("complaint_count", 0)
        cf = nhtsa.get("crash_or_fire_reports", 0)
        safety = nhtsa.get("safety_ratings") or {}
        if rc or cc or cf:
            lines.append(f"Open recalls: {rc} | Complaints: {cc} | Crash/fire reports: {cf}")
            if rc > 0 and nhtsa.get("recalls"):
                for r in nhtsa["recalls"][:2]:
                    comp = r.get("component", "")
                    if comp:
                        lines.append(f"  — {comp}")
            if cc > 0 and nhtsa.get("complaints_by_component"):
                top = sorted(nhtsa["complaints_by_component"].items(), key=lambda x: -x[1])[:2]
                for comp, cnt in top:
                    lines.append(f"  — {comp}: {cnt} reports")
        if safety.get("overall_rating"):
            lines.append(f"NCAP safety rating: {safety['overall_rating']}/5")
        if not (rc or cc or cf or safety.get("overall_rating")):
            lines.append("No NHTSA data in this run. Add VIN (used cars) for recall lookup.")
    else:
        lines.append("Add your VIN for used cars to check recalls. Run analysis for complaint and safety data.")

    lines.extend([
        "",
        "━━━ NEXT STEPS ━━━",
        "",
        "• Get out-the-door quotes from multiple dealers; compare every line item.",
        "• Separate vehicle price, financing, trade-in, and add-ons before signing.",
        "• Set GROQ_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY in .env for LLM-powered analysis.",
        "",
        "— Generated from static knowledge base (demo mode)",
    ])

    return "\n".join(lines)


def _build_context(input_data: Dict[str, Any], analysis: Optional[Dict[str, Any]]) -> str:
    """Build a structured context string for the LLM."""
    parts = [
        "## Vehicle Selection",
        f"- Year: {input_data.get('year', 'N/A')}",
        f"- Make: {input_data.get('make', 'N/A')}",
        f"- Model: {input_data.get('model', 'N/A')}",
        f"- Condition: {input_data.get('vehicle_condition', 'N/A')}",
        f"- Quoted price: ${input_data.get('price', 0):,.0f}",
        f"- Ownership horizon: {input_data.get('years', 5)} years",
    ]
    if input_data.get("vin"):
        parts.append(f"- VIN: {input_data['vin']}")

    if analysis:
        parts.append("\n## Analysis Results")
        pa = analysis.get("price_analysis") or {}
        if pa.get("verdict"):
            parts.append(f"- Price verdict: {pa.get('verdict')} (vs market low/mid/high)")
            r = pa.get("ranges") or {}
            if r:
                parts.append(f"  Market range: ${r.get('low', 0):,.0f} - ${r.get('high', 0):,.0f}")

        hc = analysis.get("hidden_costs") or {}
        if hc.get("total_true_cost") is not None:
            parts.append(f"- 5-year true cost: ${hc.get('total_true_cost', 0):,.0f}")

        timing = analysis.get("timing") or {}
        if timing.get("assessment"):
            parts.append(f"- Timing: {timing.get('assessment')}")

        reviews = analysis.get("reviews") or {}
        if reviews.get("score"):
            parts.append(f"- Sentiment: {reviews.get('score', 0):.1f}/5 ({reviews.get('sentiment_label', '')})")

        gotchas = analysis.get("gotchas") or {}
        by_sev = gotchas.get("by_severity") or {}
        total_gotchas = sum(len(v) for v in by_sev.values())
        if total_gotchas:
            parts.append(f"- Gotchas to watch: {total_gotchas} items")

        nhtsa = (reviews.get("nhtsa") or {})
        if nhtsa.get("recall_count") or nhtsa.get("complaint_count"):
            parts.append(f"- NHTSA: {nhtsa.get('recall_count', 0)} recalls, {nhtsa.get('complaint_count', 0)} complaints")

    return "\n".join(parts)


def _call_gemini(context: str, model_name: str) -> str:
    """Call Google Gemini API once. Returns generated text or raises."""
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        model_name or "gemini-2.0-flash",
        system_instruction=GROQ_SYSTEM_PROMPT,
        generation_config={"max_output_tokens": 800, "temperature": 0.5},
    )
    resp = model.generate_content(context)
    if not resp or not resp.text:
        return ""
    return resp.text.strip()


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if exception is a rate limit (429) error."""
    err_str = str(exc).lower()
    if "429" in err_str or "rate limit" in err_str or "rate_limit" in err_str:
        return True
    if hasattr(exc, "status_code") and getattr(exc, "status_code") == 429:
        return True
    if hasattr(exc, "response") and getattr(exc.response, "status_code", None) == 429:
        return True
    return False


# System prompt for car-buying advisor — easy, useful, conversational
GROQ_SYSTEM_PROMPT = """You are a friendly car-buying advisor helping someone decide whether to buy a specific vehicle. Your goal is to make car information easy to understand and useful for real buyers.

**Your style:**
• Use plain language — avoid jargon. If you must use a term (e.g. "depreciation"), briefly explain it.
• Be concise but helpful. Lead with the most important takeaway, then add details.
• Use short paragraphs and bullet points. Easy to scan.
• Be honest and balanced — mention pros and cons, not just positives.
• Give actionable advice: what to do next, what to ask the dealer, what to watch for.

**What to cover (when relevant):**
• **Price verdict** — Is this a fair deal? Should they negotiate? By how much?
• **True cost** — What will they really pay over 5 years? Biggest cost drivers?
• **Timing** — Is now a good time to buy? When might prices be better?
• **Owner experience** — What do real owners love or complain about?
• **Gotchas** — Hidden fees, add-ons, or dealer tricks to avoid.
• **Safety** — Recalls, complaints, crash data if available.
• **Next steps** — Concrete actions: get OTD quotes, compare line items, etc.

**Always end with a clear "What to do next" section** — 2–4 specific actions the buyer should take (e.g. get out-the-door quotes, negotiate X, ask about Y, avoid Z).

**Tone:** Helpful, knowledgeable, and reassuring — like a trusted friend who knows cars."""


def _call_groq(context: str, model_name: str, messages: Optional[List[Dict[str, str]]] = None) -> str:
    """Call Groq API with rate limit retry. Returns generated text or raises."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )

    if messages is None:
        api_messages = [
            {"role": "system", "content": GROQ_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ]
    else:
        api_messages = [{"role": "system", "content": GROQ_SYSTEM_PROMPT}] + messages

    last_error = None
    for attempt in range(GROQ_RATE_LIMIT_MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=api_messages,
                max_tokens=800,
                temperature=0.5,
            )
            choice = resp.choices[0] if resp.choices else None
            return (choice.message.content or "").strip() if choice else ""
        except Exception as e:
            last_error = e
            if _is_rate_limit_error(e) and attempt < GROQ_RATE_LIMIT_MAX_RETRIES:
                delay = min(
                    GROQ_RATE_LIMIT_BASE_DELAY * (2 ** attempt) + random.uniform(0, 2),
                    GROQ_RATE_LIMIT_MAX_DELAY,
                )
                print(f"[AI Analysis] Groq 429 rate limit — sleeping {delay:.0f}s before retry {attempt + 1}/{GROQ_RATE_LIMIT_MAX_RETRIES}")
                time.sleep(delay)
            else:
                raise
    if last_error:
        raise last_error
    return ""


def run_ai_chat(
    input_data: Dict[str, Any],
    analysis: Optional[Dict[str, Any]],
    messages: List[Dict[str, str]],
    user_message: str,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Multi-turn chat about the vehicle. Uses Groq (or fallback) with conversation history.
    messages: list of {role: "user"|"assistant", content: "..."}
    Returns { "text": "...", "model": "...", "error": "..." }.
    """
    context = _build_context(input_data, analysis)
    groq_key = os.getenv("GROQ_API_KEY")

    if groq_key and OpenAI is not None:
        try:
            model_name = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            # Build: [user: context] + conversation history + [user: new message]
            chat_messages: List[Dict[str, str]] = [
                {"role": "user", "content": f"Vehicle and analysis context:\n\n{context}\n\n---\nThe user may ask follow-up questions. Answer based on this context. Be helpful and concise."}
            ]
            chat_messages.extend(messages)
            chat_messages.append({"role": "user", "content": user_message})
            text = _call_groq("", model_name, messages=chat_messages)
            if text:
                return {"text": text, "model": model_name}
        except Exception as e:
            print("[AI Chat] Groq failed:", type(e).__name__, str(e)[:150])
            return {"error": str(e)[:200]}

    return {"error": "AI chat requires GROQ_API_KEY. Set it in .env to enable follow-up questions."}


def _call_openai(context: str, model_name: str, base_url: Optional[str]) -> str:
    """Call OpenAI API. Returns generated text or raises."""
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": GROQ_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        max_tokens=800,
        temperature=0.5,
    )
    choice = resp.choices[0] if resp.choices else None
    return (choice.message.content or "").strip() if choice else ""


def run_ai_analysis(
    input_data: Dict[str, Any],
    analysis: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call an LLM to produce a concise analysis of the vehicle selection.
    Tries Groq first if GROQ_API_KEY is set, then Gemini, then OpenAI, then static fallback.
    Returns { "text": "...", "model": "...", "demo": bool, "error": "..." }.
    """
    context = _build_context(input_data, analysis)
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    print("[AI Analysis] GROQ_API_KEY present:", bool(groq_key), "| GEMINI_API_KEY present:", bool(gemini_key), "| OPENAI_API_KEY present:", bool(openai_key), "| OpenAI module:", OpenAI is not None)

    # Prioritize Groq (fast, good rate limits) if key is set
    if groq_key and OpenAI is not None:
        try:
            model_name = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            print("[AI Analysis] Calling Groq API, model:", model_name)
            text = _call_groq(context, model_name)
            if text:
                print("[AI Analysis] Groq API success, response length:", len(text))
                return {"text": text, "model": model_name, "demo": False}
            print("[AI Analysis] Groq API returned empty response")
        except Exception as e:
            print("[AI Analysis] Groq API failed:", type(e).__name__, str(e)[:200])

    # Fallback to Gemini
    if gemini_key and genai is not None:
        try:
            model_name = model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            print("[AI Analysis] Calling Gemini API, model:", model_name)
            text = _call_gemini(context, model_name)
            if text:
                print("[AI Analysis] Gemini API success, response length:", len(text))
                return {"text": text, "model": model_name, "demo": False}
            print("[AI Analysis] Gemini API returned empty response")
        except Exception as e:
            print("[AI Analysis] Gemini API failed:", type(e).__name__, str(e)[:200])

    # Fallback to OpenAI
    if openai_key and OpenAI is not None:
        try:
            model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            print("[AI Analysis] Calling OpenAI API, model:", model_name)
            base_url = os.getenv("OPENAI_BASE_URL") or None
            text = _call_openai(context, model_name, base_url)
            if text:
                print("[AI Analysis] OpenAI API success, response length:", len(text))
                return {"text": text, "model": model_name, "demo": False}
            print("[AI Analysis] OpenAI API returned empty response")
        except Exception as e:
            print("[AI Analysis] OpenAI API failed:", type(e).__name__, str(e)[:200])

    # Static fallback
    print("[AI Analysis] Using static fallback (demo mode)")
    text = _build_static_analysis(input_data, analysis)
    return {"text": text, "model": "static", "demo": True}
