"""
Navigation layer: routes requests using Gemini Free only.
Routes tasks and formats payloads. NEVER performs calculations or business logic.
"""

import os
import json

# Optional: use Gemini for routing/classification. Fallback to deterministic map if no key.
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

ALLOWED_ACTIONS = {
    "ingest", "clean", "analyze", "report", "deliver", "health", "full_pipeline"
}


def _route_without_llm(action: str, payload: dict) -> dict:
    """Deterministic fallback when Gemini is unavailable."""
    action = (action or "").strip().lower()
    if action not in ALLOWED_ACTIONS:
        action = "full_pipeline"
    return {
        "route": action,
        "tool": _action_to_tool(action),
        "formatted_payload": {"action": action, **payload},
        "message": f"Routed to {action}."
    }


def _action_to_tool(action: str) -> str:
    m = {
        "ingest": "ingest_data",
        "clean": "clean_data",
        "analyze": "analyze",
        "report": "generate_report",
        "deliver": "send_payload",
        "health": "health_check",
        "full_pipeline": "full_pipeline",
    }
    return m.get(action, "full_pipeline")


def route(request: dict) -> dict:
    """
    Route a request to the appropriate tool. Uses Gemini Free only for
    classification/formatting. Returns route, tool name, formatted_payload (display only),
    and message. No calculations; no schema changes.
    """
    action = (request.get("action") or "").strip().lower()
    payload = request.get("payload") or {}
    options = request.get("options") or {}

    if action not in ALLOWED_ACTIONS:
        action = "full_pipeline"

    api_key = os.environ.get("GEMINI_API_KEY")
    if not GEMINI_AVAILABLE or not api_key:
        return _route_without_llm(action, payload)

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"""You are a router. You must ONLY classify the user request and return a JSON object.
Allowed actions: {", ".join(sorted(ALLOWED_ACTIONS))}.
User action: "{action}". User payload keys: {list(payload.keys())}.

Return ONLY valid JSON with exactly these keys (no calculations, no new metrics):
- "route": one of the allowed actions
- "message": one short sentence describing the route (e.g. "Running full pipeline.")
- "formatted_payload": copy the user payload for forwarding; do NOT add or change numeric fields.

Example: {{"route": "full_pipeline", "message": "Running full pipeline.", "formatted_payload": {{}}}}
"""
        response = model.generate_content(prompt)
        text = (response.text or "").strip()
        # Extract JSON from response (may be wrapped in markdown)
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        route_name = (data.get("route") or action).strip().lower()
        if route_name not in ALLOWED_ACTIONS:
            route_name = action
        return {
            "route": route_name,
            "tool": _action_to_tool(route_name),
            "formatted_payload": data.get("formatted_payload") or payload,
            "message": data.get("message") or f"Routed to {route_name}."
        }
    except Exception:
        return _route_without_llm(action, payload)
