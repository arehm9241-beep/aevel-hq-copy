"""
B.L.A.S.T. Analytics — Web app entrypoint.
Render-ready; cron/webhook trigger; health check; dashboard (calendar, tasks, notes, AI).
Email/password authentication with SQLite database.
Zoho Mail (hello.aevel@zohomail.com) for notifications; admin area to control what emails go to whom.
"""

import json
import os
import sys
import uuid
import sqlite3
from pathlib import Path
from functools import wraps

# Ensure project root on path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production-" + str(uuid.uuid4()))

# Zoho Mail (free zohomail.com) — emails sent from hello.aevel@zohomail.com
ZOHO_EMAIL = os.environ.get("ZOHO_EMAIL", "hello.aevel@zohomail.com")
ZOHO_PASSWORD = os.environ.get("ZOHO_PASSWORD", "")
app.config["MAIL_SERVER"] = "smtp.zoho.com"
app.config["MAIL_PORT"] = 465
app.config["MAIL_USE_SSL"] = True
app.config["MAIL_USERNAME"] = ZOHO_EMAIL
app.config["MAIL_PASSWORD"] = ZOHO_PASSWORD
app.config["MAIL_DEFAULT_SENDER"] = ("Aevel", ZOHO_EMAIL)

try:
    from flask_mail import Mail
    mail = Mail(app)
except Exception:
    mail = None

# Ensure .tmp exists
TMP_DIR = ROOT / ".tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = TMP_DIR / "app.db"


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            done INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER PRIMARY KEY,
            prefs_json TEXT DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()


def migrate_db():
    """Add new columns and tables (tasks assignee/urgency, workspace_pages, flowcharts, email_settings)."""
    conn = get_db()
    for col, ctype in [("assigned_to", "TEXT"), ("due_date", "TEXT"), ("urgency", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {ctype}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workspace_pages (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flowcharts (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            mermaid_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_type TEXT UNIQUE NOT NULL,
            enabled INTEGER DEFAULT 0,
            recipients TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS community_notes (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    for col, ctype in [
        ("time_start", "TEXT"),
        ("time_end", "TEXT"),
        ("notes", "TEXT"),
        ("is_all_day", "INTEGER"),
    ]:
        try:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} {ctype}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    # Seed email types if missing
    for etype in ("task_assigned", "due_soon", "digest"):
        try:
            conn.execute(
                "INSERT INTO email_settings (email_type, enabled, recipients) VALUES (?, 0, '')",
                (etype,),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass
    conn.close()


init_db()
migrate_db()


def login_required(f):
    """Decorator to require login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def admin_required(f):
    """Decorator to require admin session (password-protected admin box)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin"):
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function


def get_user_id():
    """Get current user ID from session."""
    return session.get("user_id")


def log_activity(user_id, action, resource_type=None, resource_id=None, details=None):
    """Persist user activity for analytics and debugging. Safe to call; never raises."""
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO activity_log (user_id, action, resource_type, resource_id, details) VALUES (?, ?, ?, ?, ?)",
            (user_id, action, resource_type, resource_id, json.dumps(details) if details is not None else None),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_email_settings():
    """Return dict of email_type -> {enabled: bool, recipients: list of emails}."""
    conn = get_db()
    rows = conn.execute("SELECT email_type, enabled, recipients FROM email_settings").fetchall()
    conn.close()
    return {
        r["email_type"]: {
            "enabled": bool(r["enabled"]),
            "recipients": [e.strip() for e in (r["recipients"] or "").split(",") if e.strip()],
        }
        for r in rows
    }


def send_app_email(email_type, subject, body_html_or_text, to_emails=None):
    """Send email via Zoho if this type is enabled and recipients exist. Uses admin list; if to_emails given (e.g. assignee), merges with admin list.
    Returns (True, None) on success, (False, None) when skipped (not configured/enabled/recipients), (False, error_message) on SMTP failure."""
    if not mail or not ZOHO_PASSWORD:
        return (False, None)
    settings = get_email_settings()
    conf = settings.get(email_type, {})
    if not conf.get("enabled"):
        return (False, None)
    admin_list = conf.get("recipients") or []
    if isinstance(admin_list, str):
        admin_list = [e.strip() for e in admin_list.split(",") if e.strip()]
    if to_emails is not None:
        extra = to_emails if isinstance(to_emails, list) else [to_emails]
        recipients = list(dict.fromkeys([e.strip() for e in extra if e and str(e).strip()] + admin_list))
    else:
        recipients = admin_list
    if not recipients:
        return (False, None)
    try:
        from flask_mail import Message
        msg = Message(subject=subject, recipients=recipients, body=body_html_or_text)
        if "<" in body_html_or_text and ">" in body_html_or_text:
            msg.html = body_html_or_text
            msg.body = body_html_or_text.replace("<br>", "\n").replace("</p>", "\n")
        mail.send(msg)
        log_activity(None, "email_sent", details={"email_type": email_type, "ok": True})
        return (True, None)
    except Exception as e:
        err_msg = str(e).strip() or "Unknown error"
        log_activity(None, "email_sent", details={"email_type": email_type, "ok": False, "error": err_msg})
        return (False, err_msg)


def run_pipeline():
    """Run full pipeline: ingest → clean → analyze → report → send_payload."""
    from tools import ingest_data, clean_data, analyze, generate_report, send_payload
    steps = [ingest_data.ingest, clean_data.clean, analyze.analyze, lambda: generate_report.generate_report(), send_payload.send_payload]
    for step in steps:
        code = step()
        if code != 0:
            return code
    return 0


@app.route("/health", methods=["GET"])
def health():
    """Health check: env and integrations. Fail fast if unreachable."""
    from tools import health_check
    code = health_check.health_check()
    if code != 0:
        return jsonify({"status": "error", "message": "Health check failed"}), 503
    return jsonify({
        "status": "ok",
        "tmp_dir": str(TMP_DIR),
        "data_source": "path" if os.environ.get("DATA_SOURCE_PATH") else ("url" if os.environ.get("DATA_SOURCE_URL") else "none"),
    }), 200


@app.route("/trigger", methods=["POST", "GET"])
def trigger():
    """Cron/webhook: route request then run pipeline or single tool."""
    from navigation.router import route
    body = request.get_json(silent=True) or {}
    req = {"action": body.get("action", "full_pipeline"), "payload": body.get("payload", {}), "options": body.get("options", {})}
    result = route(req)
    tool_name = result.get("tool", "full_pipeline")
    if tool_name == "health_check":
        from tools import health_check
        code = health_check.health_check()
        return jsonify({"route": result, "health_exit": code}), 200 if code == 0 else 503
    if tool_name == "full_pipeline":
        code = run_pipeline()
        return jsonify({"route": result, "pipeline_exit": code}), 200 if code == 0 else 500
    # Single-tool dispatch
    if tool_name == "ingest_data":
        from tools import ingest_data
        code = ingest_data.ingest()
    elif tool_name == "clean_data":
        from tools import clean_data
        code = clean_data.clean()
    elif tool_name == "analyze":
        from tools import analyze
        code = analyze.analyze()
    elif tool_name == "generate_report":
        from tools import generate_report
        code = generate_report.generate_report()
    elif tool_name == "send_payload":
        from tools import send_payload
        code = send_payload.send_payload()
    else:
        code = run_pipeline()
    return jsonify({"route": result, "tool_exit": code}), 200 if code == 0 else 500


# — Auth routes
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not email or not password:
            flash("Email and password required", "error")
            return render_template("login.html")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_email"] = user["email"]
            log_activity(user["id"], "login")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        if not email or not password:
            flash("Email and password required", "error")
            return render_template("register.html")
        if password != confirm:
            flash("Passwords do not match", "error")
            return render_template("register.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters", "error")
            return render_template("register.html")
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (email, generate_password_hash(password))
            )
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            conn.close()
            session["user_id"] = user["id"]
            session["user_email"] = user["email"]
            log_activity(user["id"], "register")
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            conn.close()
            flash("Email already registered", "error")
    return render_template("register.html")


@app.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# — Admin (password-protected; control what emails get sent and to whom)
@app.route("/admin", methods=["GET", "POST"])
def admin_page():
    if request.method == "POST":
        password = request.form.get("password") or ""
        if ADMIN_PASSWORD and password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_page"))
        flash("Invalid admin password", "error")
    if session.get("admin"):
        return render_template(
            "admin.html",
            zoho_email=ZOHO_EMAIL,
            zoho_password_configured=bool(ZOHO_PASSWORD),
        )
    return render_template("admin_login.html")


@app.route("/admin/logout", methods=["GET", "POST"])
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_page"))


@app.route("/api/admin/email-settings", methods=["GET"])
@admin_required
def api_admin_email_settings_get():
    return jsonify(get_email_settings())


@app.route("/api/admin/email-settings", methods=["PATCH"])
@admin_required
def api_admin_email_settings_update():
    data = request.get_json(silent=True) or {}
    email_type = (data.get("email_type") or "").strip()
    if not email_type:
        return jsonify({"error": "email_type required"}), 400
    conn = get_db()
    row = conn.execute("SELECT 1 FROM email_settings WHERE email_type = ?", (email_type,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "unknown email_type"}), 400
    if "enabled" in data:
        conn.execute(
            "UPDATE email_settings SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE email_type = ?",
            (1 if data["enabled"] else 0, email_type),
        )
    if "recipients" in data:
        rec = data["recipients"]
        if isinstance(rec, list):
            rec = ",".join(str(e).strip() for e in rec if str(e).strip())
        conn.execute(
            "UPDATE email_settings SET recipients = ?, updated_at = CURRENT_TIMESTAMP WHERE email_type = ?",
            (rec or "", email_type),
        )
    conn.commit()
    conn.close()
    log_activity(get_user_id(), "admin_email_settings_update", resource_type="email_settings", resource_id=email_type)
    return jsonify(get_email_settings())


# Send one email now to that type's recipients (admin)
SEND_NOW_DEFAULTS = {
    "task_assigned": ("Task assigned (test)", "<p>This is a test email for <strong>Task assigned</strong>. You received it because an admin clicked Send now.</p>"),
    "due_soon": ("Due soon reminder (test)", "<p>This is a test <strong>Due soon</strong> reminder. Tasks due soon would be listed here.</p>"),
    "digest": ("Aevel digest (test)", "<p>This is a test <strong>Digest</strong> email. A real digest would include task and activity summary.</p>"),
}


@app.route("/api/admin/send-now", methods=["POST"])
@admin_required
def api_admin_send_now():
    data = request.get_json(silent=True) or {}
    email_type = (data.get("email_type") or "").strip()
    if not email_type or email_type not in SEND_NOW_DEFAULTS:
        return jsonify({"error": "email_type required (task_assigned, due_soon, or digest)"}), 400
    subj, body = SEND_NOW_DEFAULTS.get(email_type, ("Test", "<p>Test email.</p>"))
    subject = data.get("subject") or subj
    body_html = data.get("body") or body
    ok, err = send_app_email(email_type, subject, body_html, to_emails=None)
    log_activity(get_user_id(), "admin_send_now", resource_type="email", details={"email_type": email_type, "ok": ok})
    if ok:
        return jsonify({"ok": True, "message": "Sent."}), 200
    if err:
        return jsonify({"ok": False, "message": "Send failed: " + err}), 200
    return jsonify({"ok": False, "message": "Not sent (enable this type and add recipients)."}), 200


@app.route("/api/admin/send-custom", methods=["POST"])
@admin_required
def api_admin_send_custom():
    """Send one email to a specific address with custom subject and body (admin only)."""
    data = request.get_json(silent=True) or {}
    to_email = (data.get("email") or "").strip()
    if not to_email or "@" not in to_email:
        return jsonify({"error": "Valid email required"}), 400
    subject = (data.get("subject") or "Message from Aevel").strip() or "Message from Aevel"
    body = (data.get("body") or "").strip() or "(No message)"
    if not mail or not ZOHO_PASSWORD:
        return jsonify({"ok": False, "message": "Email not configured."}), 200
    try:
        from flask_mail import Message
        msg = Message(subject=subject, recipients=[to_email], body=body)
        if "<" in body and ">" in body:
            msg.html = body
        mail.send(msg)
        log_activity(get_user_id(), "admin_send_custom", details={"to": to_email, "ok": True})
        return jsonify({"ok": True, "message": "Sent to " + to_email}), 200
    except Exception as e:
        log_activity(get_user_id(), "admin_send_custom", details={"to": to_email, "ok": False, "error": str(e)})
        return jsonify({"ok": False, "message": "Send failed: " + str(e)}), 200


@app.route("/", methods=["GET"])
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/calendar", methods=["GET"])
@login_required
def calendar_page():
    return render_template("calendar.html")


@app.route("/tasks", methods=["GET"])
@login_required
def tasks_page():
    return render_template("tasks.html")


@app.route("/notes", methods=["GET"])
@login_required
def notes_page():
    return render_template("notes.html")


@app.route("/ai", methods=["GET"])
@login_required
def ai_page():
    return redirect(url_for("integrations_page"))


@app.route("/analytics", methods=["GET"])
@login_required
def analytics_page():
    return render_template("analytics.html")


@app.route("/reports", methods=["GET"])
@login_required
def reports_page():
    return render_template("reports.html")


@app.route("/automations", methods=["GET"])
@login_required
def automations_page():
    return render_template("automations.html")


@app.route("/integrations", methods=["GET"])
@login_required
def integrations_page():
    return render_template("integrations.html")


@app.route("/settings", methods=["GET"])
@login_required
def settings_page():
    return render_template("settings.html")


@app.route("/workspace", methods=["GET"])
@login_required
def workspace_page():
    return render_template("workspace.html")


@app.route("/flowcharts", methods=["GET"])
@login_required
def flowcharts_page():
    return render_template("flowcharts.html")


@app.route("/community-notes", methods=["GET"])
@login_required
def community_notes_page():
    return render_template("community_notes.html")


@app.route("/team-tasks", methods=["GET"])
@login_required
def team_tasks_page():
    return render_template("team_tasks.html")


# — API: workspace pages (team-wide collab, Notion-like)
@app.route("/api/workspace", methods=["GET"])
@login_required
def api_workspace_list():
    user_id = get_user_id()
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, body, created_at, updated_at FROM workspace_pages WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    pages = [
        {
            "id": r["id"],
            "title": r["title"] or "",
            "body": r["body"] or "",
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return jsonify({"pages": pages})


@app.route("/api/workspace", methods=["POST"])
@login_required
def api_workspace_create():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "Untitled").strip() or "Untitled"
    body = (data.get("body") or "").strip()
    page_id = str(uuid.uuid4())
    user_id = get_user_id()
    conn = None
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO workspace_pages (id, user_id, title, body) VALUES (?, ?, ?, ?)",
            (page_id, user_id, title, body),
        )
        conn.commit()
        log_activity(user_id, "workspace_create", "workspace_page", page_id)
        return jsonify({"id": page_id, "title": title, "body": body}), 201
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"error": "Failed to create page"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/workspace/<pid>", methods=["GET"])
@login_required
def api_workspace_get(pid):
    user_id = get_user_id()
    conn = get_db()
    row = conn.execute(
        "SELECT id, title, body, created_at, updated_at FROM workspace_pages WHERE id = ? AND user_id = ?",
        (pid, user_id),
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(dict(row))


@app.route("/api/workspace/<pid>", methods=["PATCH"])
@login_required
def api_workspace_update(pid):
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM workspace_pages WHERE id = ? AND user_id = ?", (pid, user_id)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "not found"}), 404
    if "title" in data:
        title = (str(data["title"]) or "").strip() or "Untitled"
        conn.execute(
            "UPDATE workspace_pages SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (title, pid, user_id),
        )
    if "body" in data:
        conn.execute(
            "UPDATE workspace_pages SET body = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (data.get("body") or "", pid, user_id),
        )
    conn.commit()
    log_activity(user_id, "workspace_update", "workspace_page", pid)
    row = conn.execute(
        "SELECT id, title, body, created_at, updated_at FROM workspace_pages WHERE id = ? AND user_id = ?",
        (pid, user_id),
    ).fetchone()
    conn.close()
    return jsonify(dict(row))


@app.route("/api/workspace/<pid>", methods=["DELETE"])
@login_required
def api_workspace_delete(pid):
    user_id = get_user_id()
    conn = get_db()
    cur = conn.execute("DELETE FROM workspace_pages WHERE id = ? AND user_id = ?", (pid, user_id))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return jsonify({"error": "not found"}), 404
    log_activity(user_id, "workspace_delete", "workspace_page", pid)
    return jsonify({"ok": True}), 200


# — API: flowcharts (user-scoped)
@app.route("/api/flowcharts", methods=["GET"])
@login_required
def api_flowcharts_list():
    user_id = get_user_id()
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, mermaid_text, created_at, updated_at FROM flowcharts WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    items = [
        {
            "id": r["id"],
            "title": r["title"] or "",
            "mermaid_text": r["mermaid_text"] or "",
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return jsonify({"flowcharts": items})


@app.route("/api/flowcharts", methods=["POST"])
@login_required
def api_flowcharts_create():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "Untitled flowchart").strip() or "Untitled flowchart"
    mermaid_text = (data.get("mermaid_text") or "").strip()
    fc_id = str(uuid.uuid4())
    user_id = get_user_id()
    conn = None
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO flowcharts (id, user_id, title, mermaid_text) VALUES (?, ?, ?, ?)",
            (fc_id, user_id, title, mermaid_text),
        )
        conn.commit()
        log_activity(user_id, "flowchart_create", "flowchart", fc_id)
        return jsonify({"id": fc_id, "title": title, "mermaid_text": mermaid_text}), 201
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"error": "Failed to create flowchart"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/flowcharts/<fid>", methods=["GET"])
@login_required
def api_flowcharts_get(fid):
    user_id = get_user_id()
    conn = get_db()
    row = conn.execute(
        "SELECT id, title, mermaid_text, created_at, updated_at FROM flowcharts WHERE id = ? AND user_id = ?",
        (fid, user_id),
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(dict(row))


@app.route("/api/flowcharts/<fid>", methods=["PATCH"])
@login_required
def api_flowcharts_update(fid):
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM flowcharts WHERE id = ? AND user_id = ?", (fid, user_id)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "not found"}), 404
    if "title" in data:
        title = (str(data["title"]) or "").strip() or "Untitled flowchart"
        conn.execute(
            "UPDATE flowcharts SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (title, fid, user_id),
        )
    if "mermaid_text" in data:
        conn.execute(
            "UPDATE flowcharts SET mermaid_text = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (data.get("mermaid_text") or "", fid, user_id),
        )
    conn.commit()
    log_activity(user_id, "flowchart_update", "flowchart", fid)
    row = conn.execute(
        "SELECT id, title, mermaid_text, created_at, updated_at FROM flowcharts WHERE id = ? AND user_id = ?",
        (fid, user_id),
    ).fetchone()
    conn.close()
    return jsonify(dict(row))


@app.route("/api/flowcharts/<fid>", methods=["DELETE"])
@login_required
def api_flowcharts_delete(fid):
    user_id = get_user_id()
    conn = get_db()
    cur = conn.execute("DELETE FROM flowcharts WHERE id = ? AND user_id = ?", (fid, user_id))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return jsonify({"error": "not found"}), 404
    log_activity(user_id, "flowchart_delete", "flowchart", fid)
    return jsonify({"ok": True}), 200


# — API: community notes (team ideas, everyone can add and see)
@app.route("/api/community-notes", methods=["GET"])
@login_required
def api_community_notes_list():
    conn = get_db()
    rows = conn.execute("""
        SELECT n.id, n.user_id, n.title, n.body, n.created_at, u.email as author_email
        FROM community_notes n
        LEFT JOIN users u ON u.id = n.user_id
        ORDER BY n.created_at DESC
    """).fetchall()
    conn.close()
    notes = [
        {
            "id": r["id"],
            "title": r["title"] or "",
            "body": r["body"] or "",
            "created_at": r["created_at"],
            "author_email": r["author_email"] or "",
        }
        for r in rows
    ]
    return jsonify({"notes": notes})


@app.route("/api/community-notes", methods=["POST"])
@login_required
def api_community_notes_create():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "Idea").strip() or "Idea"
    body = (data.get("body") or "").strip()
    note_id = str(uuid.uuid4())
    user_id = get_user_id()
    conn = None
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO community_notes (id, user_id, title, body) VALUES (?, ?, ?, ?)",
            (note_id, user_id, title, body),
        )
        conn.commit()
        log_activity(user_id, "community_note_create", "community_note", note_id)
        return jsonify({"id": note_id, "title": title, "body": body}), 201
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"error": "Failed to create note"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/community-notes/<nid>", methods=["DELETE"])
@login_required
def api_community_notes_delete(nid):
    user_id = get_user_id()
    conn = get_db()
    cur = conn.execute("DELETE FROM community_notes WHERE id = ? AND user_id = ?", (nid, user_id))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return jsonify({"error": "not found"}), 404
    log_activity(user_id, "community_note_delete", "community_note", nid)
    return jsonify({"ok": True}), 200


# — API: team tasks (all tasks from all users, with owner)
@app.route("/api/tasks/team", methods=["GET"])
@login_required
def api_tasks_team():
    conn = get_db()
    rows = conn.execute("""
        SELECT t.id, t.text, t.done, t.assigned_to, t.due_date, t.urgency, t.created_at, u.email as owner_email
        FROM tasks t
        LEFT JOIN users u ON u.id = t.user_id
        ORDER BY t.created_at DESC
    """).fetchall()
    conn.close()
    tasks = [
        {
            "id": r["id"],
            "text": r["text"],
            "done": bool(r["done"]),
            "assigned_to": (r["assigned_to"] or "").strip(),
            "due_date": (r["due_date"] or "").strip(),
            "urgency": (r["urgency"] or "normal").strip(),
            "created_at": r["created_at"],
            "owner_email": r["owner_email"] or "",
        }
        for r in rows
    ]
    return jsonify({"tasks": tasks})


# — API: user preferences (customization)
DEFAULT_PREFS = {
    "dashboard_kpis": True,
    "dashboard_chart": True,
    "dashboard_recent": True,
    "dashboard_widgets": True,
    "compact": False,
}


def get_prefs(user_id):
    conn = get_db()
    row = conn.execute("SELECT prefs_json FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return DEFAULT_PREFS.copy()
    try:
        data = json.loads(row["prefs_json"] or "{}")
        return {**DEFAULT_PREFS, **data}
    except (TypeError, json.JSONDecodeError):
        return DEFAULT_PREFS.copy()


@app.route("/api/preferences", methods=["GET"])
@login_required
def api_preferences_get():
    return jsonify(get_prefs(get_user_id()))


@app.route("/api/preferences", methods=["PATCH"])
@login_required
def api_preferences_update():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    prefs = get_prefs(user_id)
    for k in DEFAULT_PREFS:
        if k in data:
            if k == "compact":
                prefs[k] = bool(data[k])
            elif k.startswith("dashboard_"):
                prefs[k] = bool(data[k])
    if "task_order" in data and isinstance(data["task_order"], list):
        prefs["task_order"] = [str(x) for x in data["task_order"] if x][:500]
    conn = None
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO user_preferences (user_id, prefs_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(user_id) DO UPDATE SET prefs_json = excluded.prefs_json, updated_at = CURRENT_TIMESTAMP",
            (user_id, json.dumps(prefs)),
        )
        conn.commit()
        log_activity(user_id, "preferences_update")
        return jsonify(prefs)
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"error": "Failed to save preferences"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# — API: dashboard stats
@app.route("/api/dashboard/stats", methods=["GET"])
@login_required
def api_dashboard_stats():
    user_id = get_user_id()
    conn = get_db()
    tasks = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE user_id = ?", (user_id,)).fetchone()["c"]
    tasks_done = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE user_id = ? AND done = 1", (user_id,)).fetchone()["c"]
    notes = conn.execute("SELECT COUNT(*) as c FROM notes WHERE user_id = ?", (user_id,)).fetchone()["c"]
    events = conn.execute("SELECT COUNT(*) as c FROM events WHERE user_id = ?", (user_id,)).fetchone()["c"]
    # Quick insights: tasks due in next 7 days (not done), events this week
    from datetime import datetime, timedelta
    today = datetime.utcnow().date().isoformat()
    week_later = (datetime.utcnow().date() + timedelta(days=7)).isoformat()
    tasks_due_soon = conn.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE user_id = ? AND done = 0 AND due_date IS NOT NULL AND due_date != '' AND due_date >= ? AND due_date <= ?",
        (user_id, today, week_later),
    ).fetchone()["c"]
    events_this_week = conn.execute(
        "SELECT COUNT(*) as c FROM events WHERE user_id = ? AND date >= ? AND date <= ?",
        (user_id, today, week_later),
    ).fetchone()["c"]
    # Activity this week vs last week (for comparison)
    week_ago = (datetime.utcnow().date() - timedelta(days=7)).isoformat()
    activity_this_week = conn.execute(
        "SELECT COUNT(*) as c FROM activity_log WHERE user_id = ? AND date(created_at) >= ?",
        (user_id, today),
    ).fetchone()["c"]
    activity_last_week = conn.execute(
        "SELECT COUNT(*) as c FROM activity_log WHERE user_id = ? AND date(created_at) >= ? AND date(created_at) < ?",
        (user_id, week_ago, today),
    ).fetchone()["c"]
    # Last 7 days counts for sparkline (oldest to newest)
    last_7_days = []
    for i in range(6, -1, -1):
        d = (datetime.utcnow().date() - timedelta(days=i)).isoformat()
        c = conn.execute(
            "SELECT COUNT(*) as c FROM activity_log WHERE user_id = ? AND date(created_at) = ?",
            (user_id, d),
        ).fetchone()["c"]
        last_7_days.append(c)
    conn.close()
    return jsonify({
        "tasks_total": tasks,
        "tasks_done": tasks_done,
        "notes_count": notes,
        "events_count": events,
        "tasks_due_soon": tasks_due_soon,
        "events_this_week": events_this_week,
        "activity_this_week": activity_this_week,
        "activity_last_week": activity_last_week,
        "last_7_days": last_7_days,
    })


# — API: tasks (with assignee, due_date, urgency; task_assigned email when assigned_to set)
def _task_row_to_json(r):
    out = {
        "id": r["id"],
        "text": r["text"],
        "done": bool(r["done"]),
        "assigned_to": (r["assigned_to"] or "").strip() if "assigned_to" in r.keys() else "",
        "due_date": (r["due_date"] or "").strip() if "due_date" in r.keys() else "",
        "urgency": (r["urgency"] or "normal").strip() if "urgency" in r.keys() else "normal",
    }
    if "created_at" in r.keys() and r["created_at"]:
        out["created_at"] = r["created_at"]
    return out


@app.route("/api/tasks", methods=["GET"])
@login_required
def api_tasks_list():
    user_id = get_user_id()
    conn = get_db()
    rows = conn.execute(
        "SELECT id, text, done, assigned_to, due_date, urgency, created_at FROM tasks WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    try:
        tasks = [_task_row_to_json(dict(r)) for r in rows]
    except Exception:
        tasks = [{"id": r["id"], "text": r["text"], "done": bool(r["done"]), "assigned_to": "", "due_date": "", "urgency": "normal"} for r in rows]
    return jsonify({"tasks": tasks})


@app.route("/api/tasks", methods=["POST"])
@login_required
def api_tasks_create():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    task_id = str(uuid.uuid4())
    assigned_raw = data.get("assigned_to")
    if isinstance(assigned_raw, list):
        assigned_to = ",".join(str(e).strip() for e in assigned_raw if str(e).strip())
    else:
        assigned_to = (assigned_raw or "").strip()
    due_date = (data.get("due_date") or "").strip()
    urgency = (data.get("urgency") or "normal").strip() or "normal"
    conn = get_db()
    conn.execute(
        "INSERT INTO tasks (id, user_id, text, assigned_to, due_date, urgency) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, user_id, text, assigned_to, due_date, urgency),
    )
    conn.commit()
    conn.close()
    log_activity(user_id, "task_create", "task", task_id)
    if assigned_to:
        emails = [e.strip() for e in assigned_to.split(",") if e.strip()]
        send_app_email(  # returns (ok, err); we don't surface err to user here
            "task_assigned",
            "Task assigned: " + text[:50],
            f"<p>You were assigned a task:</p><p><strong>{text}</strong></p><p>Urgency: {urgency}</p><p>Due: {due_date or 'Not set'}</p>",
            to_emails=emails,
        )  # (ok, err) ignored
    return jsonify({"id": task_id, "text": text, "done": False, "assigned_to": assigned_to, "due_date": due_date, "urgency": urgency}), 201


@app.route("/api/tasks/<tid>", methods=["PATCH"])
@login_required
def api_tasks_update(tid):
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    conn = get_db()
    row = conn.execute("SELECT id, text, done, assigned_to, due_date, urgency FROM tasks WHERE id = ? AND user_id = ?", (tid, user_id)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "not found"}), 404
    row = dict(row)
    prev_assigned = (row.get("assigned_to") or "").strip()
    if "done" in data:
        conn.execute("UPDATE tasks SET done = ? WHERE id = ? AND user_id = ?", (1 if data["done"] else 0, tid, user_id))
    if "text" in data:
        text = str(data["text"]).strip()
        if text:
            conn.execute("UPDATE tasks SET text = ? WHERE id = ? AND user_id = ?", (text, tid, user_id))
            row["text"] = text
    if "assigned_to" in data:
        assigned_raw = data.get("assigned_to")
        if isinstance(assigned_raw, list):
            assigned_to = ",".join(str(e).strip() for e in assigned_raw if str(e).strip())
        else:
            assigned_to = (assigned_raw or "").strip()
        conn.execute("UPDATE tasks SET assigned_to = ? WHERE id = ? AND user_id = ?", (assigned_to, tid, user_id))
        row["assigned_to"] = assigned_to
        if assigned_to and assigned_to != prev_assigned:
            emails = [e.strip() for e in assigned_to.split(",") if e.strip()]
            send_app_email(  # (ok, err) ignored
                "task_assigned",
                "Task assigned: " + (row.get("text") or "")[:50],
                f"<p>You were assigned a task:</p><p><strong>{row.get('text', '')}</strong></p><p>Urgency: {row.get('urgency') or 'normal'}</p><p>Due: {row.get('due_date') or 'Not set'}</p>",
                to_emails=emails,
            )
    if "due_date" in data:
        due_date = (str(data["due_date"]) or "").strip()
        conn.execute("UPDATE tasks SET due_date = ? WHERE id = ? AND user_id = ?", (due_date, tid, user_id))
        row["due_date"] = due_date
    if "urgency" in data:
        urgency = (str(data["urgency"]) or "normal").strip() or "normal"
        conn.execute("UPDATE tasks SET urgency = ? WHERE id = ? AND user_id = ?", (urgency, tid, user_id))
        row["urgency"] = urgency
    conn.commit()
    row = conn.execute("SELECT id, text, done, assigned_to, due_date, urgency FROM tasks WHERE id = ? AND user_id = ?", (tid, user_id)).fetchone()
    conn.close()
    log_activity(user_id, "task_update", "task", tid)
    return jsonify(_task_row_to_json(dict(row)))


@app.route("/api/tasks/<tid>", methods=["DELETE"])
@login_required
def api_tasks_delete(tid):
    user_id = get_user_id()
    conn = get_db()
    conn.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (tid, user_id))
    conn.commit()
    conn.close()
    log_activity(user_id, "task_delete", "task", tid)
    return jsonify({"ok": True}), 200


# — API: notes
@app.route("/api/notes", methods=["GET"])
@login_required
def api_notes_list():
    user_id = get_user_id()
    conn = get_db()
    rows = conn.execute("SELECT id, title, body, created_at FROM notes WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
    conn.close()
    notes = [{"id": r["id"], "title": r["title"], "body": r["body"] or "", "created_at": r["created_at"] or ""} for r in rows]
    return jsonify({"notes": notes})


@app.route("/api/notes", methods=["POST"])
@login_required
def api_notes_create():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    note_id = str(uuid.uuid4())
    body = (data.get("body") or "").strip()
    conn = get_db()
    conn.execute("INSERT INTO notes (id, user_id, title, body) VALUES (?, ?, ?, ?)", (note_id, user_id, title, body))
    conn.commit()
    conn.close()
    log_activity(user_id, "note_create", "note", note_id)
    return jsonify({"id": note_id, "title": title, "body": body}), 201


@app.route("/api/notes/<nid>", methods=["DELETE"])
@login_required
def api_notes_delete(nid):
    user_id = get_user_id()
    conn = get_db()
    conn.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (nid, user_id))
    conn.commit()
    conn.close()
    log_activity(user_id, "note_delete", "note", nid)
    return jsonify({"ok": True}), 200


# — API: events (calendar)
def _event_row_to_json(r):
    out = {"id": r["id"], "date": r["date"], "title": r["title"]}
    if "time_start" in r.keys():
        out["time_start"] = (r["time_start"] or "").strip() or None
    if "time_end" in r.keys():
        out["time_end"] = (r["time_end"] or "").strip() or None
    if "notes" in r.keys():
        out["notes"] = (r["notes"] or "").strip() or None
    if "is_all_day" in r.keys():
        out["is_all_day"] = bool(r["is_all_day"])
    return out


@app.route("/api/events", methods=["GET"])
@login_required
def api_events_list():
    user_id = get_user_id()
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, date, title, time_start, time_end, notes, is_all_day FROM events WHERE user_id = ? ORDER BY date",
            (user_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute("SELECT id, date, title FROM events WHERE user_id = ? ORDER BY date", (user_id,)).fetchall()
    conn.close()
    events = [_event_row_to_json(dict(r)) for r in rows]
    return jsonify({"events": events})


@app.route("/api/events", methods=["POST"])
@login_required
def api_events_create():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    date = (data.get("date") or "").strip()
    title = (data.get("title") or "").strip()
    if not date or not title:
        return jsonify({"error": "date and title required"}), 400
    event_id = str(uuid.uuid4())
    time_start = (data.get("time_start") or "").strip() or None
    time_end = (data.get("time_end") or "").strip() or None
    notes = (data.get("notes") or "").strip() or None
    is_all_day = 1 if data.get("is_all_day", True) else 0
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO events (id, user_id, date, title, time_start, time_end, notes, is_all_day) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, user_id, date, title, time_start, time_end, notes, is_all_day),
        )
    except sqlite3.OperationalError:
        conn.execute("INSERT INTO events (id, user_id, date, title) VALUES (?, ?, ?, ?)", (event_id, user_id, date, title))
    conn.commit()
    conn.close()
    log_activity(user_id, "event_create", "event", event_id)
    out = {"id": event_id, "date": date, "title": title}
    if time_start is not None:
        out["time_start"] = time_start
    if time_end is not None:
        out["time_end"] = time_end
    if notes is not None:
        out["notes"] = notes
    out["is_all_day"] = bool(is_all_day)
    return jsonify(out), 201


@app.route("/api/events/<eid>", methods=["PATCH"])
@login_required
def api_events_update(eid):
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, date, title, time_start, time_end, notes, is_all_day FROM events WHERE id = ? AND user_id = ?",
            (eid, user_id),
        ).fetchone()
    except sqlite3.OperationalError:
        row = conn.execute("SELECT id, date, title FROM events WHERE id = ? AND user_id = ?", (eid, user_id)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "not found"}), 404
    row = dict(row)
    date = (data.get("date") or "").strip() if "date" in data else row["date"]
    title = (data.get("title") or "").strip() if "title" in data else row["title"]
    if not date or not title:
        conn.close()
        return jsonify({"error": "date and title required"}), 400
    time_start = (data.get("time_start") or "").strip() or None if "time_start" in data else (row.get("time_start") or None)
    time_end = (data.get("time_end") or "").strip() or None if "time_end" in data else (row.get("time_end") or None)
    notes = (data.get("notes") or "").strip() or None if "notes" in data else (row.get("notes") or None)
    is_all_day = (1 if data.get("is_all_day", True) else 0) if "is_all_day" in data else (1 if row.get("is_all_day", 1) else 0)
    try:
        conn.execute(
            "UPDATE events SET date = ?, title = ?, time_start = ?, time_end = ?, notes = ?, is_all_day = ? WHERE id = ? AND user_id = ?",
            (date, title, time_start, time_end, notes, is_all_day, eid, user_id),
        )
    except sqlite3.OperationalError:
        conn.execute("UPDATE events SET date = ?, title = ? WHERE id = ? AND user_id = ?", (date, title, eid, user_id))
    conn.commit()
    log_activity(user_id, "event_update", "event", eid)
    conn.close()
    out = {"id": eid, "date": date, "title": title}
    out["time_start"] = time_start
    out["time_end"] = time_end
    out["notes"] = notes
    out["is_all_day"] = bool(is_all_day)
    return jsonify(out), 200


@app.route("/api/events/<eid>", methods=["DELETE"])
@login_required
def api_events_delete(eid):
    user_id = get_user_id()
    conn = get_db()
    conn.execute("DELETE FROM events WHERE id = ? AND user_id = ?", (eid, user_id))
    conn.commit()
    conn.close()
    log_activity(user_id, "event_delete", "event", eid)
    return jsonify({"ok": True}), 200


# — API: activity feed (recent actions for dashboard)
@app.route("/api/activity/recent", methods=["GET"])
@login_required
def api_activity_recent():
    user_id = get_user_id()
    limit = min(int(request.args.get("limit", 20)), 50)
    conn = get_db()
    rows = conn.execute(
        """SELECT id, user_id, action, resource_type, resource_id, details, created_at
           FROM activity_log WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    conn.close()
    items = []
    for r in rows:
        details = None
        if r["details"]:
            try:
                details = json.loads(r["details"])
            except (TypeError, json.JSONDecodeError):
                pass
        items.append({
            "id": r["id"],
            "action": r["action"],
            "resource_type": r["resource_type"] or "",
            "resource_id": r["resource_id"] or "",
            "details": details,
            "created_at": r["created_at"],
        })
    return jsonify({"items": items})


# — API: batch complete tasks
@app.route("/api/tasks/batch-complete", methods=["POST"])
@login_required
def api_tasks_batch_complete():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    done = data.get("done", True)
    if not isinstance(ids, list):
        return jsonify({"error": "ids must be a list"}), 400
    ids = [str(i).strip() for i in ids if i]
    if not ids:
        return jsonify({"ok": True, "updated": 0}), 200
    conn = get_db()
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"UPDATE tasks SET done = ? WHERE user_id = ? AND id IN ({placeholders})",
        (1 if done else 0, user_id, *ids),
    )
    updated = cur.rowcount
    conn.commit()
    for tid in ids:
        log_activity(user_id, "task_update", "task", tid, details={"batch_complete": done})
    conn.close()
    return jsonify({"ok": True, "updated": updated}), 200


# — API: batch delete tasks
@app.route("/api/tasks/batch-delete", methods=["POST"])
@login_required
def api_tasks_batch_delete():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    if not isinstance(ids, list):
        return jsonify({"error": "ids must be a list"}), 400
    ids = [str(i).strip() for i in ids if i]
    if not ids:
        return jsonify({"ok": True, "deleted": 0}), 200
    conn = get_db()
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"DELETE FROM tasks WHERE user_id = ? AND id IN ({placeholders})",
        (user_id, *ids),
    )
    deleted = cur.rowcount
    conn.commit()
    for tid in ids:
        log_activity(user_id, "task_delete", "task", tid)
    conn.close()
    return jsonify({"ok": True, "deleted": deleted}), 200


# — API: export notes as CSV
@app.route("/api/notes/export", methods=["GET"])
@login_required
def api_notes_export():
    import csv as csv_module
    import io
    user_id = get_user_id()
    fmt = (request.args.get("format") or "csv").strip().lower()
    if fmt != "csv":
        return jsonify({"error": "format must be csv"}), 400
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, body, created_at FROM notes WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    buf = io.StringIO()
    w = csv_module.writer(buf)
    w.writerow(["Title", "Body", "Created"])
    for r in rows:
        w.writerow([
            (r["title"] or "").replace("\r", ""),
            (r["body"] or "").replace("\r", "").replace("\n", " "),
            r["created_at"] or "",
        ])
    from flask import Response
    return Response(buf.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": "attachment; filename=aevel-reports.csv",
    })


# — API: AI helpers (Gemini)
@app.route("/api/ai/calendar/optimize", methods=["POST"])
@login_required
def api_ai_calendar_optimize():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    events = data.get("events") or []
    from tools import ai_service
    suggestions, err = ai_service.optimize_schedule(events, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"suggestions": suggestions}), 200


@app.route("/api/ai/calendar/summarize", methods=["POST"])
@login_required
def api_ai_calendar_summarize():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    events = data.get("events") or []
    scope = data.get("scope") or "week"
    from tools import ai_service
    text, err = ai_service.summarize_events(events, scope, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"summary": text}), 200


@app.route("/api/ai/calendar/extract", methods=["POST"])
@login_required
def api_ai_calendar_extract():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    from tools import ai_service
    events, err = ai_service.extract_events_from_text(text, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"events": events or []}), 200


@app.route("/api/ai/tasks/break-down", methods=["POST"])
@login_required
def api_ai_tasks_break_down():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    from tools import ai_service
    subtasks, err = ai_service.break_down_task(text, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"subtasks": subtasks or []}), 200


@app.route("/api/ai/tasks/prioritize", methods=["POST"])
@login_required
def api_ai_tasks_prioritize():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    tasks = data.get("tasks") or []
    from tools import ai_service
    result, err = ai_service.prioritize_tasks(tasks, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"order": result or []}), 200


@app.route("/api/ai/tasks/estimate", methods=["POST"])
@login_required
def api_ai_tasks_estimate():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    from tools import ai_service
    result, err = ai_service.estimate_effort(text, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(result or {}), 200


@app.route("/api/ai/dashboard/insights", methods=["POST"])
@login_required
def api_ai_dashboard_insights():
    user_id = get_user_id()
    stats = request.get_json(silent=True) or {}
    conn = get_db()
    rows = conn.execute(
        "SELECT action, created_at FROM activity_log WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
        (user_id,),
    ).fetchall()
    conn.close()
    activity_items = [{"action": r["action"], "created_at": r["created_at"]} for r in rows]
    from tools import ai_service
    text, err = ai_service.dashboard_insights(stats, activity_items, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"insights": text}), 200


@app.route("/api/ai/analytics/explain", methods=["POST"])
@login_required
def api_ai_analytics_explain():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    metric = (data.get("metric") or "").strip()
    value = data.get("value", "")
    context = (data.get("context") or "").strip()
    if not metric:
        return jsonify({"error": "metric required"}), 400
    from tools import ai_service
    text, err = ai_service.explain_metric(metric, value, context, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"explanation": text}), 200


@app.route("/api/ai/analytics/summarize", methods=["POST"])
@login_required
def api_ai_analytics_summarize():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    from tools import ai_service
    text, err = ai_service.summarize_campaign(data, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"summary": text}), 200


@app.route("/api/ai/analytics/suggest", methods=["POST"])
@login_required
def api_ai_analytics_suggest():
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    from tools import ai_service
    suggestions, err = ai_service.suggest_optimizations(data, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"suggestions": suggestions or []}), 200


# — API: AI query (routing/formatting only)
@app.route("/api/ai/query", methods=["POST"])
@login_required
def api_ai_query():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query required"}), 400
    from navigation.router import route
    req = {"action": "full_pipeline", "payload": {"query": query}, "options": {}}
    result = route(req)
    return jsonify({
        "route": result.get("route"),
        "tool": result.get("tool"),
        "message": result.get("message"),
        "formatted_payload": result.get("formatted_payload"),
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
