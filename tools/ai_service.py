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
        # Use gemini-2.5-flash (latest model with best quota availability)
        model = genai.GenerativeModel("gemini-2.5-flash")
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


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE AI
# ═══════════════════════════════════════════════════════════════════════════

def summarize_pipeline_run(run_data: dict, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Summarize a pipeline run: what happened, outputs, any issues."""
    payload = json.dumps({
        "run_id": run_data.get("id"),
        "status": run_data.get("status"),
        "duration": run_data.get("duration"),
        "started_at": run_data.get("started_at"),
        "exit_code": run_data.get("exit_code"),
        "config": run_data.get("config", {}),
        "outputs": [{"name": o.get("name"), "type": o.get("type"), "size": o.get("size")} for o in run_data.get("outputs", [])[:10]],
    })
    prompt = f"""Summarize this pipeline run in 3-4 sentences. Be concise and technical.
Include: what was processed, how long it took, what outputs were generated, and whether it succeeded.
If there were issues, mention them clearly. Neutral tone.
Run data:
{payload}
"""
    return _call_gemini(prompt, "summarize_pipeline_run", user_id, log_fn)


def explain_pipeline_failure(run_data: dict, logs: list = None, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Explain a pipeline failure in plain language with potential causes."""
    payload = json.dumps({
        "status": run_data.get("status"),
        "exit_code": run_data.get("exit_code"),
        "config": run_data.get("config", {}),
        "logs": (logs or [])[-20:],  # Last 20 log entries
    })
    prompt = f"""This pipeline run failed or had issues. Explain in plain language:
1. What likely went wrong (2-3 sentences)
2. Potential causes (2-3 bullet points)
3. Suggested next steps (1-2 bullets)

Be helpful but avoid certainty. Use phrases like "may have", "possibly", "consider checking".
Data:
{payload}
"""
    return _call_gemini(prompt, "explain_pipeline_failure", user_id, log_fn)


def suggest_pipeline_optimizations(run_history: list, user_id=None, log_fn=None) -> tuple[list | None, str | None]:
    """Suggest pipeline optimizations based on run history."""
    payload = json.dumps([{
        "status": r.get("status"),
        "duration": r.get("duration"),
        "config": r.get("config", {}),
    } for r in run_history[-10:]])
    prompt = f"""Based on this pipeline run history, suggest 2-4 optimizations.
Focus on: efficiency, scheduling, configuration improvements, data quality.
Return ONLY valid JSON array of strings. Each suggestion should be actionable.
No markdown.
History:
{payload}
"""
    text, err = _call_gemini(prompt, "suggest_pipeline_optimizations", user_id, log_fn)
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


# ═══════════════════════════════════════════════════════════════════════════
# REPORTS AI
# ═══════════════════════════════════════════════════════════════════════════

def summarize_report(title: str, body: str, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Generate a concise summary of a report."""
    prompt = f"""Summarize this report in 2-3 sentences. Extract the key points and conclusions.
Neutral, professional tone. No filler.
Title: {title[:200]}
Content: {body[:3000]}
"""
    return _call_gemini(prompt, "summarize_report", user_id, log_fn)


def rewrite_report_for_audience(title: str, body: str, audience: str, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Rewrite a report for a specific audience (executive, marketing, technical)."""
    audience_guidance = {
        "executive": "Focus on business impact, key decisions needed, and bottom-line results. Be concise. Use bullet points.",
        "marketing": "Focus on performance metrics, campaign insights, and actionable recommendations. Use accessible language.",
        "technical": "Include technical details, methodology, and data specifics. Be precise."
    }
    guidance = audience_guidance.get(audience, audience_guidance["executive"])
    prompt = f"""Rewrite this report for a {audience} audience.
{guidance}
Keep the core information but adjust tone, detail level, and structure.
Generate a complete rewrite, not a summary.

Original title: {title[:200]}
Original content: {body[:3000]}
"""
    return _call_gemini(prompt, "rewrite_report", user_id, log_fn)


def extract_report_takeaways(title: str, body: str, user_id=None, log_fn=None) -> tuple[list | None, str | None]:
    """Extract key takeaways and action items from a report."""
    prompt = f"""Extract key takeaways from this report. Return ONLY valid JSON:
{{"takeaways": ["key point 1", "key point 2", ...], "action_items": ["action 1", "action 2", ...]}}
Limit to 5 takeaways and 3 action items max. Be specific and actionable.
No markdown.

Title: {title[:200]}
Content: {body[:3000]}
"""
    text, err = _call_gemini(prompt, "extract_report_takeaways", user_id, log_fn)
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


# ═══════════════════════════════════════════════════════════════════════════
# TASKS & WORKLOAD AI
# ═══════════════════════════════════════════════════════════════════════════

def summarize_workload(tasks: list, events: list, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Summarize current workload: tasks, events, potential conflicts."""
    payload = json.dumps({
        "tasks": [{"text": t.get("text"), "due_date": t.get("due_date"), "urgency": t.get("urgency"), "done": t.get("done")} for t in tasks[:30]],
        "events": [{"title": e.get("title"), "date": e.get("date")} for e in events[:20]],
    })
    prompt = f"""Analyze this workload and provide a brief summary (3-4 sentences):
- Current task load and urgency distribution
- Upcoming events and potential busy periods
- Any conflicts or overload risks
- Overall assessment (manageable, heavy, light)

Be factual, not motivational. Neutral tone.
Data:
{payload}
"""
    return _call_gemini(prompt, "summarize_workload", user_id, log_fn)


def suggest_focus(tasks: list, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Suggest what to focus on based on tasks and deadlines."""
    active = [t for t in tasks if not t.get("done")][:20]
    payload = json.dumps([{"text": t.get("text"), "due_date": t.get("due_date"), "urgency": t.get("urgency")} for t in active])
    prompt = f"""Based on these tasks, suggest what to focus on today in 2-3 sentences.
Consider: urgency, deadlines, dependencies. Be specific about which tasks to prioritize.
Neutral, helpful tone. No motivational fluff.
Tasks:
{payload}
"""
    return _call_gemini(prompt, "suggest_focus", user_id, log_fn)


# ═══════════════════════════════════════════════════════════════════════════
# NOTES & WORKSPACE AI
# ═══════════════════════════════════════════════════════════════════════════

def summarize_note(title: str, body: str, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Summarize a long note into key points."""
    prompt = f"""Summarize this note in 2-3 sentences. Extract the main ideas.
Title: {title[:200]}
Content: {body[:4000]}
"""
    return _call_gemini(prompt, "summarize_note", user_id, log_fn)


def extract_action_items(content: str, user_id=None, log_fn=None) -> tuple[list | None, str | None]:
    """Extract action items from note content."""
    prompt = f"""Extract action items from this content. Return ONLY valid JSON array of strings.
Look for: tasks mentioned, things to do, follow-ups needed, decisions to make.
Max 8 items. Be specific.
No markdown.
Content:
{content[:4000]}
"""
    text, err = _call_gemini(prompt, "extract_action_items", user_id, log_fn)
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


def find_related_themes(notes: list, user_id=None, log_fn=None) -> tuple[list | None, str | None]:
    """Find common themes across notes."""
    payload = json.dumps([{"title": n.get("title"), "snippet": (n.get("body") or "")[:300]} for n in notes[:15]])
    prompt = f"""Analyze these notes and identify 3-5 common themes or related topics.
Return ONLY valid JSON array: [{{"theme": "theme name", "notes": ["related note titles"], "summary": "one sentence"}}]
No markdown.
Notes:
{payload}
"""
    text, err = _call_gemini(prompt, "find_related_themes", user_id, log_fn)
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


# ═══════════════════════════════════════════════════════════════════════════
# AI BRIEFING (DASHBOARD)
# ═══════════════════════════════════════════════════════════════════════════

def generate_briefing(stats: dict, tasks: list, events: list, activity: list, user_id=None, log_fn=None) -> tuple[dict | None, str | None]:
    """Generate a comprehensive AI briefing for the dashboard."""
    payload = json.dumps({
        "stats": {
            "tasks_total": stats.get("tasks_total"),
            "tasks_done": stats.get("tasks_done"),
            "tasks_overdue": stats.get("tasks_overdue"),
            "events_this_week": stats.get("events_this_week"),
        },
        "upcoming_tasks": [{"text": t.get("text"), "due_date": t.get("due_date")} for t in tasks[:10] if not t.get("done")],
        "upcoming_events": [{"title": e.get("title"), "date": e.get("date")} for e in events[:10]],
        "recent_activity": [a.get("action") for a in activity[:10]],
    })
    prompt = f"""Generate a brief daily system summary. Return ONLY valid JSON:
{{
  "summary": "2-3 sentence overview of current state",
  "highlights": ["key point 1", "key point 2", "key point 3"],
  "risks": ["risk or deadline if any"],
  "suggested_actions": ["suggested next action 1", "suggested next action 2"]
}}
Be concise, factual, professional. No motivational language.
No markdown.
Data:
{payload}
"""
    text, err = _call_gemini(prompt, "generate_briefing", user_id, log_fn)
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


# ═══════════════════════════════════════════════════════════════════════════
# GLOBAL AI COMMAND ROUTING
# ═══════════════════════════════════════════════════════════════════════════

def route_ai_command(query: str, user_id=None, log_fn=None) -> tuple[dict | None, str | None]:
    """Route a natural language command to the appropriate AI subsystem."""
    prompt = f"""Classify this user query and determine the appropriate action.
Return ONLY valid JSON:
{{
  "intent": "summarize_pipeline|explain_data|summarize_tasks|summarize_calendar|generate_report|ask_question|unknown",
  "target": "pipeline|analytics|tasks|calendar|reports|notes|general",
  "parameters": {{}},
  "response_type": "text|list|structured"
}}
No markdown.
Query: {query[:500]}
"""
    text, err = _call_gemini(prompt, "route_ai_command", user_id, log_fn)
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


def answer_general_query(query: str, context: dict = None, user_id=None, log_fn=None) -> tuple[str | None, str | None]:
    """Answer a general question using available context."""
    ctx = json.dumps(context or {})[:2000]
    prompt = f"""Answer this question concisely based on the available context.
Be helpful but acknowledge limitations. If you don't have enough information, say so.
Stay focused on data analytics and business operations topics.
2-4 sentences max.

Question: {query[:500]}
Context: {ctx}
"""
    return _call_gemini(prompt, "answer_general_query", user_id, log_fn)
