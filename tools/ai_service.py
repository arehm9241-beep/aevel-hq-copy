"""
AI service: Gemini-powered helpers for calendar, tasks, dashboard, analytics.
Uses GEMINI_API_KEY. Handles failures, rate limiting, logs to activity_log.
"""

import os
import json
import time
from collections import defaultdict

# Rate limit: max requests per minute per action type
_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX = 30
_rate_counts = defaultdict(list)


def _check_rate_limit(action: str) -> bool:
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW
    _rate_counts[action] = [t for t in _rate_counts[action] if t > window_start]
    if len(_rate_counts[action]) >= _RATE_LIMIT_MAX:
        return False
    _rate_counts[action].append(now)
    return True


def _call_gemini(prompt: str, action: str, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Call Gemini. Returns (result_text, error_message). Logs success/failure."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "GEMINI_API_KEY not set"
    if not _check_rate_limit(action):
        return None, "Rate limit exceeded. Try again in a minute."
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        text = (response.text or "").strip()
        if log_fn:
            log_fn(user_id, f"ai_{action}", details={"ok": True, "action": action})
        return text, None
    except Exception as e:
        err = str(e).strip() or "Unknown error"
        if log_fn:
            log_fn(user_id, f"ai_{action}", details={"ok": False, "action": action, "error": err})
        return None, err


def optimize_schedule(events: list, user_id=None, log_fn=None) -> tuple[list | None, str | None]:
    """Suggest better time placement for events. Returns (suggestions_list, error)."""
    payload = json.dumps([{"id": e.get("id"), "date": e.get("date"), "title": e.get("title"), "time_start": e.get("time_start"), "time_end": e.get("time_end")} for e in events[:20]])
    prompt = f"""You are a scheduling assistant. Given these events, suggest a more balanced schedule.
Return ONLY valid JSON array. Each item: {{"id": "event_id", "suggested_date": "YYYY-MM-DD", "suggested_time_start": "HH:MM or null for all-day", "suggested_time_end": "HH:MM or null", "reason": "one short sentence"}}.
No markdown, no explanation. Events:
{payload}
"""
    text, err = _call_gemini(prompt, "optimize_schedule", user_id, log_fn)
    if err:
        return None, err
    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip()), None
    except json.JSONDecodeError:
        return None, "Could not parse AI response"


def summarize_events(events: list, scope: str, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Summarize events in natural language. scope: 'day' or 'week'."""
    payload = json.dumps([{"date": e.get("date"), "title": e.get("title"), "time_start": e.get("time_start")} for e in events[:50]])
    prompt = f"""Summarize these {scope} events in 2-4 concise sentences. Neutral, technical tone. No marketing. Just the facts.
Events:
{payload}
"""
    text, err = _call_gemini(prompt, "summarize_events", user_id, log_fn)
    return text, err


def extract_events_from_text(raw_text: str, user_id=None, log_fn=None) -> tuple[list | None, str | None]:
    """Extract events from pasted text. Returns (list of {{date, title, time_start?, time_end?}}, error)."""
    prompt = f"""Extract calendar events from this text. Return ONLY valid JSON array.
Each item: {{"date": "YYYY-MM-DD", "title": "event title", "time_start": "HH:MM or null", "time_end": "HH:MM or null"}}.
Use today's date if only time mentioned. Infer reasonable dates if ambiguous. No markdown.
Text:
{raw_text[:3000]}
"""
    text, err = _call_gemini(prompt, "extract_events", user_id, log_fn)
    if err:
        return None, err
    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip()), None
    except json.JSONDecodeError:
        return None, "Could not parse AI response"


def break_down_task(task_text: str, user_id=None, log_fn=None) -> tuple[list | None, str | None]:
    """Break task into subtasks. Returns (list of strings, error)."""
    prompt = f"""Break this task into 3-6 concrete subtasks. Return ONLY valid JSON array of strings.
Example: ["Subtask 1", "Subtask 2"]
Task: {task_text[:500]}
"""
    text, err = _call_gemini(prompt, "break_down_task", user_id, log_fn)
    if err:
        return None, err
    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        out = json.loads(text.strip())
        return [str(x) for x in out] if isinstance(out, list) else None, None
    except json.JSONDecodeError:
        return None, "Could not parse AI response"


def prioritize_tasks(tasks: list, user_id=None, log_fn=None) -> tuple[list | None, str | None]:
    """Reorder tasks by priority with reasoning. Returns (list of {{id, order, reason}}, error)."""
    payload = json.dumps([{"id": t.get("id"), "text": t.get("text"), "due_date": t.get("due_date"), "urgency": t.get("urgency")} for t in tasks[:30]])
    prompt = f"""Prioritize these tasks. Return ONLY valid JSON array. Each item: {{"id": "task_id", "order": 1-based position, "reason": "one short sentence"}}.
Order by urgency, due date, and dependencies. No markdown.
Tasks:
{payload}
"""
    text, err = _call_gemini(prompt, "prioritize_tasks", user_id, log_fn)
    if err:
        return None, err
    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip()), None
    except json.JSONDecodeError:
        return None, "Could not parse AI response"


def estimate_effort(task_text: str, user_id=None, log_fn=None) -> tuple[dict | None, str | None]:
    """Estimate effort: low/medium/high and optional time. Returns ({{level, time_est?, explanation}}, error)."""
    prompt = f"""Estimate effort for this task. Return ONLY valid JSON: {{"level": "low"|"medium"|"high", "time_est": "e.g. 30 min" or null, "explanation": "one short sentence"}}.
Task: {task_text[:500]}
"""
    text, err = _call_gemini(prompt, "estimate_effort", user_id, log_fn)
    if err:
        return None, err
    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip()), None
    except json.JSONDecodeError:
        return None, "Could not parse AI response"


def dashboard_insights(stats: dict, activity_items: list, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Generate daily/weekly activity insights. Calm, technical, no marketing."""
    payload = json.dumps({
        "tasks_total": stats.get("tasks_total"),
        "tasks_done": stats.get("tasks_done"),
        "events_this_week": stats.get("events_this_week"),
        "activity_this_week": stats.get("activity_this_week"),
        "activity_last_week": stats.get("activity_last_week"),
        "last_7_days": stats.get("last_7_days"),
        "recent_actions": [a.get("action") for a in activity_items[:15]],
    })
    prompt = f"""Analyze this user activity. Write 2-4 short sentences. Identify: high task density days, overload, gaps, trends.
Neutral, technical. No motivational copy. No "Great job". Just observations.
Data:
{payload}
"""
    text, err = _call_gemini(prompt, "dashboard_insights", user_id, log_fn)
    return text, err


def explain_metric(metric_name: str, value, context: str, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Plain-language explanation of a metric."""
    prompt = f"""Explain this metric in 1-2 sentences. Plain language, neutral.
Metric: {metric_name}
Value: {value}
Context: {context[:300]}
"""
    text, err = _call_gemini(prompt, "explain_metric", user_id, log_fn)
    return text, err


def summarize_campaign(data: dict, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Summarize campaign/analytics performance from data."""
    payload = json.dumps(data)[:2500]
    prompt = f"""Summarize this campaign/analytics data in 2-3 sentences. Neutral, factual. No marketing fluff.
Data:
{payload}
"""
    text, err = _call_gemini(prompt, "summarize_campaign", user_id, log_fn)
    return text, err


def suggest_optimizations(data: dict, user_id=None, log_fn=None) -> tuple[list | None, str | None]:
    """Suggest optimizations based on trends. Clearly labeled as suggestions."""
    payload = json.dumps(data)[:2500]
    prompt = f"""Based on this data, suggest 2-4 concrete optimizations. Return ONLY valid JSON array of strings.
Label each as suggestion. No markdown.
Data:
{payload}
"""
    text, err = _call_gemini(prompt, "suggest_optimizations", user_id, log_fn)
    if err:
        return None, err
    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        out = json.loads(text.strip())
        return [str(x) for x in out] if isinstance(out, list) else None, None
    except json.JSONDecodeError:
        return None, "Could not parse AI response"
