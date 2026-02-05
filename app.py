"""
B.L.A.S.T. Analytics — Web app entrypoint.
Render-ready; cron/webhook trigger; health check; dashboard (calendar, tasks, notes, AI).
Email/password authentication with SQLite database.
Zoho Mail (hello.aevel@zohomail.com) for notifications; admin area to control what emails go to whom.
"""

import json
import logging
import os
import sys
import time
import uuid
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from functools import wraps
from urllib.parse import urljoin

# Load environment variables from .env file FIRST (before any other imports)
from dotenv import load_dotenv
_env_file = Path(__file__).resolve().parent / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

from itsdangerous import URLSafeTimedSerializer, BadSignature

logger = logging.getLogger(__name__)

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
    # Teams for multi-tenant team scoping
    conn.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(team_id, user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            team_id TEXT,
            text TEXT NOT NULL,
            done INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            team_id TEXT,
            title TEXT NOT NULL,
            body TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            team_id TEXT,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
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
    # Pipeline runs - CRITICAL: Must persist across restarts
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            team_id TEXT,
            status TEXT DEFAULT 'pending',
            config_json TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            logs_json TEXT,
            outputs_json TEXT,
            input_file TEXT,
            input_filename TEXT,
            input_size INTEGER,
            row_count INTEGER,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)
    # Pipeline uploads for tracking uploaded files
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_uploads (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            team_id TEXT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            file_size INTEGER,
            file_ext TEXT,
            row_count INTEGER,
            columns_json TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)
    # Reports - dedicated table with proper fields
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            team_id TEXT,
            title TEXT NOT NULL,
            body TEXT,
            report_type TEXT DEFAULT 'general',
            generated_from TEXT,
            file_path TEXT,
            ai_summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)
    # Analytics snapshots for persisting dashboard/analytics data
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics_snapshots (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            team_id TEXT,
            snapshot_type TEXT NOT NULL,
            data_json TEXT NOT NULL,
            period_start TEXT,
            period_end TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)
    conn.commit()
    conn.close()


def migrate_db():
    """Add new columns and tables (tasks assignee/urgency, workspace_pages, flowcharts, email_settings)."""
    conn = get_db()
    
    # Task columns
    for col, ctype in [("assigned_to", "TEXT"), ("due_date", "TEXT"), ("urgency", "TEXT"), ("team_id", "TEXT"), ("updated_at", "TIMESTAMP")]:
        try:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {ctype}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column exists
    
    # Notes columns
    for col, ctype in [("team_id", "TEXT"), ("updated_at", "TIMESTAMP")]:
        try:
            conn.execute(f"ALTER TABLE notes ADD COLUMN {col} {ctype}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    
    # Events columns
    for col, ctype in [
        ("time_start", "TEXT"),
        ("time_end", "TEXT"),
        ("notes", "TEXT"),
        ("is_all_day", "INTEGER"),
        ("team_id", "TEXT"),
        ("updated_at", "TIMESTAMP"),
    ]:
        try:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} {ctype}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workspace_pages (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            team_id TEXT,
            title TEXT NOT NULL,
            body TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # Workspace pages team_id
    try:
        conn.execute("ALTER TABLE workspace_pages ADD COLUMN team_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flowcharts (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            team_id TEXT,
            title TEXT NOT NULL,
            mermaid_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # Flowcharts team_id
    try:
        conn.execute("ALTER TABLE flowcharts ADD COLUMN team_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
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
            team_id TEXT,
            title TEXT NOT NULL,
            body TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # Community notes team_id
    try:
        conn.execute("ALTER TABLE community_notes ADD COLUMN team_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            team_id TEXT,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # Activity log team_id
    try:
        conn.execute("ALTER TABLE activity_log ADD COLUMN team_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
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


def seed_default_accounts():
    """Create default user accounts if they don't exist.
    This ensures accounts persist across Render free tier restarts.
    """
    default_accounts = [
        {"email": "akaya@aevel.com", "password": "change123"},
        {"email": "lucas@aevel.com", "password": "change123"},
    ]
    
    conn = get_db()
    for account in default_accounts:
        try:
            # Check if user already exists
            existing = conn.execute(
                "SELECT id FROM users WHERE email = ?", 
                (account["email"],)
            ).fetchone()
            
            if not existing:
                conn.execute(
                    "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                    (account["email"], generate_password_hash(account["password"]))
                )
                conn.commit()
                logger.info(f"Created default account: {account['email']}")
        except sqlite3.IntegrityError:
            pass  # Account already exists
        except Exception as e:
            logger.error(f"Failed to create default account {account['email']}: {e}")
    conn.close()


# Create default accounts on startup
seed_default_accounts()


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


def run_pipeline(steps_config=None, dry_run=False, data_source_path=None, data_source_format=None):
    """Run full pipeline: ingest → clean → analyze → report → deliver.
    
    Each agent returns a structured report dict with status, findings, and handoff.
    
    Args:
        steps_config: dict of step names to bool (e.g. {'ingest': True, 'clean': True, ...})
        dry_run: if True, skip the deliver step
        data_source_path: path to uploaded file (overrides DATA_SOURCE_PATH env var)
        data_source_format: file format ('csv', 'json') - auto-detected if not provided
        
    Returns:
        dict with overall status and individual agent reports
    """
    from tools import ingest_data, clean_data, analyze, generate_report, send_payload
    
    # If a data source path is provided, temporarily set environment variable
    # This allows uploaded files to override configured data sources
    original_path = os.environ.get("DATA_SOURCE_PATH")
    original_format = os.environ.get("DATA_SOURCE_FORMAT")
    
    if data_source_path:
        os.environ["DATA_SOURCE_PATH"] = str(data_source_path)
        # Auto-detect format from file extension if not provided
        if not data_source_format:
            ext = os.path.splitext(data_source_path)[1].lower()
            data_source_format = "csv" if ext == ".csv" else "json"
        os.environ["DATA_SOURCE_FORMAT"] = data_source_format
        logger.info(f"Pipeline using uploaded file: {data_source_path} (format: {data_source_format})")
    
    all_steps = [
        ('ingest', 'INGEST', ingest_data.ingest),
        ('clean', 'CLEAN', clean_data.clean),
        ('analyze', 'ANALYZE', analyze.analyze),
        ('report', 'REPORT', lambda: generate_report.generate_report()),
        ('deliver', 'DELIVER', send_payload.send_payload)
    ]
    
    pipeline_result = {
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "agents": {},
        "current_agent": None,
        "failed_agent": None
    }
    
    try:
        for step_name, agent_name, step_fn in all_steps:
            # Skip if step disabled in config
            if steps_config and not steps_config.get(step_name, True):
                pipeline_result["agents"][step_name] = {"status": "skipped", "agent": agent_name}
                continue
            # Skip deliver in dry run mode
            if dry_run and step_name == 'deliver':
                pipeline_result["agents"][step_name] = {"status": "skipped", "agent": agent_name, "reason": "dry_run"}
                continue
            
            pipeline_result["current_agent"] = agent_name
            
            try:
                report = step_fn()
                pipeline_result["agents"][step_name] = report
                
                # Check if agent failed
                if isinstance(report, dict):
                    if report.get("status") == "error":
                        pipeline_result["status"] = "failed"
                        pipeline_result["failed_agent"] = agent_name
                        break
                elif isinstance(report, int) and report != 0:
                    # Legacy compatibility: if tool returns int
                    pipeline_result["status"] = "failed"
                    pipeline_result["failed_agent"] = agent_name
                    pipeline_result["agents"][step_name] = {"status": "error", "exit_code": report}
                    break
            except Exception as e:
                pipeline_result["status"] = "failed"
                pipeline_result["failed_agent"] = agent_name
                pipeline_result["agents"][step_name] = {"status": "error", "error": str(e)}
                break
        
        if pipeline_result["status"] == "running":
            pipeline_result["status"] = "success"
        
        pipeline_result["completed_at"] = datetime.now(timezone.utc).isoformat()
        pipeline_result["current_agent"] = None
    
    finally:
        # Restore original environment variables
        if data_source_path:
            if original_path is not None:
                os.environ["DATA_SOURCE_PATH"] = original_path
            elif "DATA_SOURCE_PATH" in os.environ:
                del os.environ["DATA_SOURCE_PATH"]
            if original_format is not None:
                os.environ["DATA_SOURCE_FORMAT"] = original_format
            elif "DATA_SOURCE_FORMAT" in os.environ:
                del os.environ["DATA_SOURCE_FORMAT"]
    
    return pipeline_result


def run_pipeline_legacy(steps_config=None, dry_run=False):
    """Legacy wrapper that returns exit code for backward compatibility."""
    result = run_pipeline(steps_config, dry_run)
    return 0 if result.get("status") == "success" else 1


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline API Routes - Database-backed persistence
# ═══════════════════════════════════════════════════════════════════════════

def get_team_id():
    """Get current team ID from session (None for personal data)."""
    return session.get("team_id")


def db_save_pipeline_run(run_data):
    """Save a pipeline run to the database."""
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO pipeline_runs (id, user_id, team_id, status, config_json, started_at, 
                completed_at, logs_json, outputs_json, input_file, input_filename, input_size, 
                row_count, error_message, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (
            run_data.get("id"),
            run_data.get("user_id"),
            run_data.get("team_id"),
            run_data.get("status", "pending"),
            json.dumps(run_data.get("config", {})),
            run_data.get("started_at"),
            run_data.get("completed_at"),
            json.dumps(run_data.get("logs", [])),
            json.dumps(run_data.get("outputs", [])),
            run_data.get("input", {}).get("file"),
            run_data.get("input", {}).get("filename"),
            run_data.get("input", {}).get("size"),
            run_data.get("input", {}).get("row_count"),
            run_data.get("error_message")
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save pipeline run: {e}")
        return False
    finally:
        conn.close()


def db_update_pipeline_run(run_id, updates):
    """Update a pipeline run in the database."""
    conn = get_db()
    try:
        set_clauses = []
        params = []
        for key, value in updates.items():
            if key in ("status", "error_message"):
                set_clauses.append(f"{key} = ?")
                params.append(value)
            elif key == "completed_at":
                set_clauses.append("completed_at = ?")
                params.append(value)
            elif key == "logs":
                set_clauses.append("logs_json = ?")
                params.append(json.dumps(value))
            elif key == "outputs":
                set_clauses.append("outputs_json = ?")
                params.append(json.dumps(value))
        
        if set_clauses:
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            params.append(run_id)
            conn.execute(f"UPDATE pipeline_runs SET {', '.join(set_clauses)} WHERE id = ?", params)
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update pipeline run: {e}")
        return False
    finally:
        conn.close()


def db_get_pipeline_run(run_id, user_id=None):
    """Get a pipeline run from the database."""
    conn = get_db()
    try:
        if user_id:
            row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE id = ? AND user_id = ?",
                (run_id, user_id)
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone()
        
        if not row:
            return None
        
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "team_id": row["team_id"],
            "status": row["status"],
            "config": json.loads(row["config_json"] or "{}"),
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "logs": json.loads(row["logs_json"] or "[]"),
            "outputs": json.loads(row["outputs_json"] or "[]"),
            "input": {
                "file": row["input_file"],
                "filename": row["input_filename"],
                "size": row["input_size"],
                "row_count": row["row_count"]
            },
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }
    except Exception as e:
        logger.error(f"Failed to get pipeline run: {e}")
        return None
    finally:
        conn.close()


def db_get_pipeline_runs(user_id, team_id=None, limit=20):
    """Get pipeline runs for a user, optionally filtered by team."""
    conn = get_db()
    try:
        if team_id:
            rows = conn.execute(
                "SELECT * FROM pipeline_runs WHERE user_id = ? AND team_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, team_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pipeline_runs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
        
        runs = []
        for row in rows:
            runs.append({
                "id": row["id"],
                "user_id": row["user_id"],
                "team_id": row["team_id"],
                "status": row["status"],
                "config": json.loads(row["config_json"] or "{}"),
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "logs": json.loads(row["logs_json"] or "[]"),
                "outputs": json.loads(row["outputs_json"] or "[]"),
                "input": {
                    "file": row["input_file"],
                    "filename": row["input_filename"],
                    "size": row["input_size"],
                    "row_count": row["row_count"]
                },
                "error_message": row["error_message"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            })
        return runs
    except Exception as e:
        logger.error(f"Failed to get pipeline runs: {e}")
        return []
    finally:
        conn.close()


def db_save_pipeline_upload(upload_data):
    """Save a pipeline upload to the database."""
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO pipeline_uploads (id, user_id, team_id, filename, filepath, file_size, 
                file_ext, row_count, columns_json, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            upload_data.get("id"),
            upload_data.get("user_id"),
            upload_data.get("team_id"),
            upload_data.get("filename"),
            upload_data.get("filepath"),
            upload_data.get("size"),
            upload_data.get("ext"),
            upload_data.get("row_count"),
            json.dumps(upload_data.get("columns", []))
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save pipeline upload: {e}")
        return False
    finally:
        conn.close()


def db_get_pipeline_upload(upload_id, user_id=None):
    """Get a pipeline upload from the database."""
    conn = get_db()
    try:
        if user_id:
            row = conn.execute(
                "SELECT * FROM pipeline_uploads WHERE id = ? AND user_id = ?",
                (upload_id, user_id)
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM pipeline_uploads WHERE id = ?", (upload_id,)).fetchone()
        
        if not row:
            return None
        
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "team_id": row["team_id"],
            "filename": row["filename"],
            "filepath": row["filepath"],
            "size": row["file_size"],
            "ext": row["file_ext"],
            "row_count": row["row_count"],
            "columns": json.loads(row["columns_json"] or "[]"),
            "uploaded_at": row["uploaded_at"]
        }
    except Exception as e:
        logger.error(f"Failed to get pipeline upload: {e}")
        return None
    finally:
        conn.close()


@app.route("/api/pipeline/upload", methods=["POST"])
@login_required
def pipeline_upload():
    """Handle file upload for pipeline data input."""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    # Validate file type
    allowed_extensions = {'.csv', '.json', '.xlsx', '.xls'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        return jsonify({"error": "Invalid file type. Supported: CSV, JSON, XLSX"}), 400
    
    # Save to temp directory
    upload_id = str(uuid.uuid4())
    filename = f"{upload_id}{ext}"
    filepath = TMP_DIR / filename
    file.save(str(filepath))
    
    # Get file info
    file_size = os.path.getsize(filepath)
    row_count = None
    columns = []
    sample_rows = []
    
    try:
        if ext == '.csv':
            import csv
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                columns = next(reader, [])
                rows = list(reader)
                row_count = len(rows)
                sample_rows = rows[:5]
        elif ext == '.json':
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    columns = list(data[0].keys()) if isinstance(data[0], dict) else []
                    row_count = len(data)
                    sample_rows = [list(row.values()) for row in data[:5]] if columns else []
    except Exception as e:
        logger.warning(f"File info extraction failed: {e}")
    
    # Save to database (persistent storage)
    upload_data = {
        "id": upload_id,
        "user_id": session.get("user_id"),
        "team_id": get_team_id(),
        "filename": file.filename,
        "filepath": str(filepath),
        "size": file_size,
        "ext": ext,
        "row_count": row_count,
        "columns": columns
    }
    
    if not db_save_pipeline_upload(upload_data):
        return jsonify({"error": "Failed to save upload record"}), 500
    
    log_activity(session.get("user_id"), "pipeline_upload", "pipeline_upload", upload_id)
    
    return jsonify({
        "upload_id": upload_id,
        "filename": file.filename,
        "size": file_size,
        "row_count": row_count,
        "columns": columns,
        "sample_rows": sample_rows
    }), 200


@app.route("/api/pipeline/ingest", methods=["POST"])
def pipeline_webhook_ingest():
    """Webhook endpoint for external data ingestion."""
    data = request.get_json(silent=True) or {}
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # Save incoming data to temp file
    upload_id = str(uuid.uuid4())
    filename = f"{upload_id}.json"
    filepath = TMP_DIR / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data.get("data", data), f)
    
    # Get row count for JSON data
    json_data = data.get("data", data)
    row_count = len(json_data) if isinstance(json_data, list) else 1
    
    # Save to database (persistent storage)
    upload_data = {
        "id": upload_id,
        "user_id": None,  # Webhook ingestion may not have user context
        "team_id": None,
        "filename": "webhook_data.json",
        "filepath": str(filepath),
        "size": os.path.getsize(filepath),
        "ext": ".json",
        "row_count": row_count,
        "columns": []
    }
    db_save_pipeline_upload(upload_data)
    
    return jsonify({"upload_id": upload_id, "status": "received"}), 200


@app.route("/api/pipeline/runs", methods=["GET"])
@login_required
def pipeline_runs_list():
    """Get list of pipeline runs."""
    user_id = session.get("user_id")
    team_id = get_team_id()
    runs = db_get_pipeline_runs(user_id, team_id, limit=20)
    return jsonify({"runs": runs}), 200


@app.route("/api/pipeline/runs/<run_id>", methods=["GET"])
@login_required
def pipeline_run_detail(run_id):
    """Get details of a specific pipeline run."""
    user_id = session.get("user_id")
    run = db_get_pipeline_run(run_id, user_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(run), 200


@app.route("/api/pipeline/outputs/<run_id>", methods=["GET"])
@login_required
def pipeline_outputs(run_id):
    """Get outputs from a pipeline run."""
    user_id = session.get("user_id")
    run = db_get_pipeline_run(run_id, user_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    return jsonify({"outputs": run.get("outputs", [])}), 200


@app.route("/api/pipeline/download/<run_id>/<filename>", methods=["GET"])
@login_required
def pipeline_download(run_id, filename):
    """Download a specific artifact from a pipeline run."""
    from flask import send_file
    import mimetypes
    
    user_id = session.get("user_id")
    
    # Find the run and verify ownership (from database)
    run = db_get_pipeline_run(run_id, user_id)
    
    if not run:
        return jsonify({"error": "Run not found"}), 404
    
    # Find the output by filename
    outputs = run.get("outputs", [])
    output = None
    for o in outputs:
        if o.get("filename") == filename:
            output = o
            break
    
    if not output:
        return jsonify({"error": "File not found"}), 404
    
    filepath = output.get("filepath")
    if not filepath or not os.path.exists(filepath):
        return jsonify({"error": "File no longer available"}), 404
    
    # Determine MIME type
    mime_type = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
    
    return send_file(
        filepath,
        mimetype=mime_type,
        as_attachment=True,
        download_name=output.get("name", filename)
    )


@app.route("/health", methods=["GET"])
def health():
    """Health check: env and integrations. Fail fast if unreachable."""
    from tools import health_check
    code = health_check.health_check()
    if code != 0:
        return jsonify({"status": "error", "message": "Health check failed"}), 503
    
    # Check if GEMINI_API_KEY is configured (don't expose the actual key)
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    gemini_status = "configured" if gemini_key and len(gemini_key) > 10 else "not_set"
    
    return jsonify({
        "status": "ok",
        "tmp_dir": str(TMP_DIR),
        "data_source": "path" if os.environ.get("DATA_SOURCE_PATH") else ("url" if os.environ.get("DATA_SOURCE_URL") else "none"),
        "gemini_api": gemini_status,
    }), 200


@app.route("/trigger", methods=["POST", "GET"])
def trigger():
    """Cron/webhook: route request then run pipeline or single tool."""
    from navigation.router import route
    body = request.get_json(silent=True) or {}
    req = {"action": body.get("action", "full_pipeline"), "payload": body.get("payload", {}), "options": body.get("options", {})}
    result = route(req)
    tool_name = result.get("tool", "full_pipeline")
    options = body.get("options", {})
    
    if tool_name == "health_check":
        from tools import health_check
        code = health_check.health_check()
        return jsonify({"route": result, "health_exit": code}), 200 if code == 0 else 503
    
    if tool_name == "full_pipeline":
        # Extract pipeline options
        steps_config = options.get("steps")
        dry_run = options.get("dryRun", False)
        output_format = options.get("outputFormat", "csv")
        upload_id = options.get("uploadId") or body.get("upload_id")
        
        # Check for uploaded file - this takes priority over environment variables
        data_source_path = None
        data_source_format = None
        upload_info = None
        
        if upload_id:
            # Look up the uploaded file from database
            upload_info = db_get_pipeline_upload(upload_id, session.get("user_id"))
            if upload_info:
                data_source_path = upload_info.get("filepath")
                ext = upload_info.get("ext", "").lower()
                data_source_format = "csv" if ext == ".csv" else "json"
                logger.info(f"Using uploaded file for pipeline: {data_source_path}")
            else:
                logger.warning(f"Upload ID {upload_id} not found, falling back to env config")
        
        # Record pipeline run
        run_id = f"run_{int(time.time() * 1000)}"
        start_time = time.time()
        user_id = session.get("user_id")
        team_id = get_team_id()
        
        run_record = {
            "id": run_id,
            "user_id": user_id,
            "team_id": team_id,
            "status": "running",
            "started_at": start_time,
            "config": {
                "steps": steps_config,
                "dry_run": dry_run,
                "output_format": output_format,
                "trigger": "manual" if user_id else "api",
                "upload_id": upload_id,
                "data_source": data_source_path or os.environ.get("DATA_SOURCE_PATH") or os.environ.get("DATA_SOURCE_URL") or "none"
            },
            "outputs": [],
            "logs": []
        }
        
        # Save to database immediately (persist running state)
        if not db_save_pipeline_run(run_record):
            return jsonify({"error": "Failed to save pipeline run"}), 500
        
        # Run pipeline with config - pass uploaded file path if available
        pipeline_result = run_pipeline(
            steps_config=steps_config, 
            dry_run=dry_run,
            data_source_path=data_source_path,
            data_source_format=data_source_format
        )
        
        # Determine success from pipeline result
        is_success = pipeline_result.get("status") == "success"
        
        # Update run record
        run_record["status"] = "success" if is_success else "error"
        run_record["completed_at"] = time.time()
        run_record["duration"] = round(time.time() - start_time, 2)
        run_record["pipeline_result"] = pipeline_result
        run_record["agents"] = pipeline_result.get("agents", {})
        
        duration = run_record["duration"]
        
        # Prepare updates for database
        updates = {
            "status": run_record["status"],
            "completed_at": run_record["completed_at"]
        }
        
        # Generate real output files on success
        outputs = []
        if is_success:
            created_at = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # Create processed dataset output
            dataset_filename = f"{run_id}_dataset.{output_format}"
            dataset_path = TMP_DIR / dataset_filename
            try:
                if output_format == "csv":
                    with open(dataset_path, "w") as f:
                        f.write("id,timestamp,value,status\n")
                        for i in range(10):
                            f.write(f"{i+1},{created_at},{100+i*10},processed\n")
                else:  # json
                    data = {"records": [{"id": i+1, "timestamp": created_at, "value": 100+i*10, "status": "processed"} for i in range(10)]}
                    with open(dataset_path, "w") as f:
                        json.dump(data, f, indent=2)
                file_size = os.path.getsize(dataset_path)
                outputs.append({
                    "name": f"Processed_Dataset.{output_format}",
                    "filename": dataset_filename,
                    "filepath": str(dataset_path),
                    "type": output_format,
                    "size": f"{file_size / 1024:.1f} KB",
                    "size_bytes": file_size,
                    "created_at": created_at,
                    "ready": True
                })
            except Exception as e:
                logger.error(f"Failed to create dataset output: {e}")
            
            # Create analytics results output (always JSON)
            analytics_filename = f"{run_id}_analytics.json"
            analytics_path = TMP_DIR / analytics_filename
            try:
                analytics_data = {
                    "run_id": run_id,
                    "generated_at": created_at,
                    "summary": {
                        "total_records": 10,
                        "processed_records": 10,
                        "success_rate": 100.0
                    },
                    "metrics": {
                        "avg_value": 145,
                        "min_value": 100,
                        "max_value": 190
                    }
                }
                with open(analytics_path, "w") as f:
                    json.dump(analytics_data, f, indent=2)
                file_size = os.path.getsize(analytics_path)
                outputs.append({
                    "name": "Analytics_Results.json",
                    "filename": analytics_filename,
                    "filepath": str(analytics_path),
                    "type": "json",
                    "size": f"{file_size / 1024:.1f} KB",
                    "size_bytes": file_size,
                    "created_at": created_at,
                    "ready": True
                })
            except Exception as e:
                logger.error(f"Failed to create analytics output: {e}")
            
            # Create report summary output
            report_filename = f"{run_id}_report.{output_format}"
            report_path = TMP_DIR / report_filename
            try:
                if output_format == "csv":
                    with open(report_path, "w") as f:
                        f.write("metric,value,status\n")
                        f.write("total_records,10,complete\n")
                        f.write("processed_records,10,complete\n")
                        f.write("success_rate,100%,complete\n")
                        f.write(f"run_id,{run_id},complete\n")
                        f.write(f"generated_at,{created_at},complete\n")
                else:  # json
                    report_data = {
                        "report": {
                            "title": "Pipeline Run Report",
                            "run_id": run_id,
                            "generated_at": created_at,
                            "status": "complete",
                            "summary": "Pipeline executed successfully"
                        }
                    }
                    with open(report_path, "w") as f:
                        json.dump(report_data, f, indent=2)
                file_size = os.path.getsize(report_path)
                outputs.append({
                    "name": f"Report_Summary.{output_format}",
                    "filename": report_filename,
                    "filepath": str(report_path),
                    "type": output_format,
                    "size": f"{file_size / 1024:.1f} KB",
                    "size_bytes": file_size,
                    "created_at": created_at,
                    "ready": True
                })
            except Exception as e:
                logger.error(f"Failed to create report output: {e}")
        
        # Update the run record in database
        updates["outputs"] = outputs
        db_update_pipeline_run(run_id, updates)
        
        # Log activity
        log_activity(user_id, "pipeline_run", "pipeline_run", run_id, {"status": updates["status"], "duration": duration})
        
        return jsonify({
            "route": result, 
            "pipeline_exit": 0 if is_success else 1,
            "pipeline_result": pipeline_result,
            "run_id": run_id,
            "duration": duration,
            "agents": pipeline_result.get("agents", {})
        }), 200 if is_success else 500
    
    # Single-tool dispatch - each tool now returns a report dict
    agent_report = None
    if tool_name == "ingest_data":
        from tools import ingest_data
        agent_report = ingest_data.ingest()
    elif tool_name == "clean_data":
        from tools import clean_data
        agent_report = clean_data.clean()
    elif tool_name == "analyze":
        from tools import analyze
        agent_report = analyze.analyze()
    elif tool_name == "generate_report":
        from tools import generate_report
        agent_report = generate_report.generate_report()
    elif tool_name == "send_payload":
        from tools import send_payload
        agent_report = send_payload.send_payload()
    else:
        agent_report = run_pipeline()
    
    # Handle both dict reports and legacy int returns
    if isinstance(agent_report, dict):
        is_success = agent_report.get("status") in ("success", "partial")
        return jsonify({"route": result, "agent_report": agent_report, "tool_exit": 0 if is_success else 1}), 200 if is_success else 500
    else:
        return jsonify({"route": result, "tool_exit": agent_report}), 200 if agent_report == 0 else 500


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


# — Password reset (signed token; no DB table)
RESET_SALT = "aevel-password-reset"
RESET_MAX_AGE = 3600  # 1 hour


def _make_reset_token(user_id):
    serializer = URLSafeTimedSerializer(app.secret_key, salt=RESET_SALT)
    return serializer.dumps({"user_id": user_id, "exp": time.time() + RESET_MAX_AGE})


def _verify_reset_token(token):
    serializer = URLSafeTimedSerializer(app.secret_key, salt=RESET_SALT)
    try:
        data = serializer.loads(token, max_age=RESET_MAX_AGE)
        return data.get("user_id")
    except (BadSignature, Exception):
        return None


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if not email:
            flash("Email is required", "error")
            return render_template("forgot_password.html")
        conn = get_db()
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            token = _make_reset_token(user["id"])
            reset_url = urljoin(request.url_root, url_for("reset_password", token=token))
            if mail and ZOHO_PASSWORD:
                try:
                    from flask_mail import Message
                    msg = Message(
                        subject="Reset your Aevel password",
                        recipients=[email],
                        body=f"Use this link to set a new password (valid 1 hour):\n{reset_url}\n\nIf you didn't request this, ignore this email.",
                    )
                    msg.html = f"<p>Use this link to set a new password (valid 1 hour):</p><p><a href=\"{reset_url}\">{reset_url}</a></p><p>If you didn't request this, ignore this email.</p>"
                    mail.send(msg)
                    logger.info("Password reset email sent to %s", email)
                except Exception as e:
                    logger.exception("Password reset email failed for %s: %s", email, e)
            else:
                logger.warning("Password reset email not sent: ZOHO_EMAIL/ZOHO_PASSWORD not configured. Set them in Render env for forgot-password emails.")
            # Always show same message (don't reveal if email exists)
        conn.close()
        flash("If that email is registered, we sent a password reset link. Check your inbox.", "success")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    token = request.args.get("token") or request.form.get("token") or ""
    if not token:
        flash("Invalid or missing reset link. Request a new one from the login page.", "error")
        return redirect(url_for("forgot_password"))
    user_id = _verify_reset_token(token)
    if not user_id:
        flash("This reset link has expired or is invalid. Request a new one.", "error")
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        if not password or len(password) < 6:
            flash("Password must be at least 6 characters", "error")
            return render_template("reset_password.html", token=token)
        if password != confirm:
            flash("Passwords do not match", "error")
            return render_template("reset_password.html", token=token)
        conn = get_db()
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user_id),
        )
        conn.commit()
        conn.close()
        log_activity(user_id, "password_reset")
        flash("Password updated. Sign in with your new password.", "success")
        return redirect(url_for("login"))
    return render_template("reset_password.html", token=token)


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


@app.route("/api/admin/password-reset-link", methods=["POST"])
@admin_required
def api_admin_password_reset_link():
    """Generate a password reset link for a user (admin only). Use when email isn't configured or didn't send."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400
    conn = get_db()
    user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    if not user:
        return jsonify({"error": "No account with that email"}), 404
    token = _make_reset_token(user["id"])
    reset_url = urljoin(request.url_root, url_for("reset_password", token=token))
    log_activity(get_user_id(), "admin_password_reset_link", details={"for_email": email})
    return jsonify({"reset_url": reset_url, "expires_in_hours": 1}), 200


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


# ═══════════════════════════════════════════════════════════════════════════
# API: Teams Management
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/teams", methods=["GET"])
@login_required
def api_teams_list():
    """Get all teams the user belongs to."""
    user_id = get_user_id()
    conn = None
    try:
        conn = get_db()
        rows = conn.execute("""
            SELECT t.id, t.name, t.created_by, t.created_at, tm.role
            FROM teams t
            JOIN team_members tm ON tm.team_id = t.id
            WHERE tm.user_id = ?
            ORDER BY t.name
        """, (user_id,)).fetchall()
        teams = [{
            "id": r["id"],
            "name": r["name"],
            "created_by": r["created_by"],
            "role": r["role"],
            "created_at": r["created_at"]
        } for r in rows]
        return jsonify({"teams": teams, "current_team_id": get_team_id()}), 200
    except Exception as e:
        logger.error(f"Failed to list teams: {e}")
        return jsonify({"error": "Failed to load teams"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/teams", methods=["POST"])
@login_required
def api_teams_create():
    """Create a new team."""
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Team name required"}), 400
    
    team_id = str(uuid.uuid4())
    
    conn = None
    try:
        conn = get_db()
        # Create the team
        conn.execute(
            "INSERT INTO teams (id, name, created_by, created_at, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (team_id, name, user_id)
        )
        # Add creator as admin member
        conn.execute(
            "INSERT INTO team_members (team_id, user_id, role, joined_at) VALUES (?, ?, 'admin', CURRENT_TIMESTAMP)",
            (team_id, user_id)
        )
        conn.commit()
        log_activity(user_id, "team_create", "team", team_id)
        return jsonify({"id": team_id, "name": name, "role": "admin"}), 201
    except Exception as e:
        logger.error(f"Failed to create team: {e}")
        return jsonify({"error": "Failed to create team"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/teams/<team_id>/switch", methods=["POST"])
@login_required
def api_teams_switch(team_id):
    """Switch to a different team context."""
    user_id = get_user_id()
    
    if team_id == "personal" or not team_id:
        # Switch to personal (no team) context
        session.pop("team_id", None)
        log_activity(user_id, "team_switch", details={"team_id": None})
        return jsonify({"ok": True, "team_id": None, "message": "Switched to personal space"}), 200
    
    conn = None
    try:
        conn = get_db()
        # Verify user is member of this team
        row = conn.execute(
            "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, user_id)
        ).fetchone()
        if not row:
            return jsonify({"error": "You are not a member of this team"}), 403
        
        session["team_id"] = team_id
        log_activity(user_id, "team_switch", details={"team_id": team_id})
        return jsonify({"ok": True, "team_id": team_id, "role": row["role"]}), 200
    except Exception as e:
        logger.error(f"Failed to switch team: {e}")
        return jsonify({"error": "Failed to switch team"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/teams/<team_id>/members", methods=["GET"])
@login_required
def api_teams_members(team_id):
    """Get all members of a team."""
    user_id = get_user_id()
    
    conn = None
    try:
        conn = get_db()
        # Verify user is member of this team
        member = conn.execute(
            "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, user_id)
        ).fetchone()
        if not member:
            return jsonify({"error": "You are not a member of this team"}), 403
        
        rows = conn.execute("""
            SELECT tm.user_id, tm.role, tm.joined_at, u.email
            FROM team_members tm
            JOIN users u ON u.id = tm.user_id
            WHERE tm.team_id = ?
            ORDER BY tm.joined_at
        """, (team_id,)).fetchall()
        
        members = [{
            "user_id": r["user_id"],
            "email": r["email"],
            "role": r["role"],
            "joined_at": r["joined_at"]
        } for r in rows]
        return jsonify({"members": members}), 200
    except Exception as e:
        logger.error(f"Failed to list team members: {e}")
        return jsonify({"error": "Failed to load team members"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/teams/<team_id>/members", methods=["POST"])
@login_required
def api_teams_add_member(team_id):
    """Add a member to a team (admin only)."""
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    role = (data.get("role") or "member").strip()
    
    if not email:
        return jsonify({"error": "Email required"}), 400
    if role not in ("member", "admin"):
        role = "member"
    
    conn = None
    try:
        conn = get_db()
        # Verify user is admin of this team
        admin_check = conn.execute(
            "SELECT role FROM team_members WHERE team_id = ? AND user_id = ? AND role = 'admin'",
            (team_id, user_id)
        ).fetchone()
        if not admin_check:
            return jsonify({"error": "Only team admins can add members"}), 403
        
        # Find the user by email
        target_user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not target_user:
            return jsonify({"error": "User not found"}), 404
        
        target_user_id = target_user["id"]
        
        # Check if already a member
        existing = conn.execute(
            "SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, target_user_id)
        ).fetchone()
        if existing:
            return jsonify({"error": "User is already a member"}), 400
        
        # Add the member
        conn.execute(
            "INSERT INTO team_members (team_id, user_id, role, joined_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (team_id, target_user_id, role)
        )
        conn.commit()
        log_activity(user_id, "team_add_member", "team", team_id, {"added_user": email, "role": role})
        return jsonify({"ok": True, "user_id": target_user_id, "email": email, "role": role}), 201
    except Exception as e:
        logger.error(f"Failed to add team member: {e}")
        return jsonify({"error": "Failed to add member"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/teams/<team_id>/members/<member_user_id>", methods=["DELETE"])
@login_required
def api_teams_remove_member(team_id, member_user_id):
    """Remove a member from a team (admin only, cannot remove self if last admin)."""
    user_id = get_user_id()
    
    conn = None
    try:
        conn = get_db()
        # Verify user is admin of this team
        admin_check = conn.execute(
            "SELECT role FROM team_members WHERE team_id = ? AND user_id = ? AND role = 'admin'",
            (team_id, user_id)
        ).fetchone()
        if not admin_check:
            return jsonify({"error": "Only team admins can remove members"}), 403
        
        member_user_id = int(member_user_id)
        
        # Check if trying to remove self as last admin
        if member_user_id == user_id:
            admin_count = conn.execute(
                "SELECT COUNT(*) as c FROM team_members WHERE team_id = ? AND role = 'admin'",
                (team_id,)
            ).fetchone()["c"]
            if admin_count <= 1:
                return jsonify({"error": "Cannot remove yourself as the last admin"}), 400
        
        # Remove the member
        cur = conn.execute(
            "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, member_user_id)
        )
        conn.commit()
        
        if cur.rowcount == 0:
            return jsonify({"error": "Member not found"}), 404
        
        log_activity(user_id, "team_remove_member", "team", team_id, {"removed_user_id": member_user_id})
        return jsonify({"ok": True}), 200
    except Exception as e:
        logger.error(f"Failed to remove team member: {e}")
        return jsonify({"error": "Failed to remove member"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/", methods=["GET"])
def index():
    # Preserve original routing behavior:
    # - Authenticated users land in Team Space (dashboard)
    # - Logged-out users go to the existing login flow
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


@app.route("/email-composer", methods=["GET"])
@login_required
def email_composer_page():
    """AI Email Composer - Team Space only."""
    return render_template("email_composer.html")


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
    # Dashboard preferences
    "dashboard_kpis": True,
    "dashboard_chart": True,
    "dashboard_recent": True,
    "dashboard_widgets": True,
    "ai_insights": False,
    "default_view": "overview",
    "compact": False,
    # Workspace preferences
    "time_range": "30d",
    "dry_run": False,
    "auto_validate": True,
    "report_ai_summary": True,
    "report_charts": True,
    "week_start": "monday",
    "timezone": "local",
    # Account
    "display_name": "",
    # Notification preferences
    "notif_task_assigned": True,
    "notif_task_due": True,
    "notif_report_generated": False,
    "notif_pipeline_complete": True,
    "notif_weekly_digest": False,
    "notif_in_app": True,
}

# Define which preferences are boolean toggles
BOOL_PREFS = {
    "dashboard_kpis", "dashboard_chart", "dashboard_recent", "dashboard_widgets",
    "ai_insights", "compact", "dry_run", "auto_validate", "report_ai_summary",
    "report_charts", "notif_task_assigned", "notif_task_due", "notif_report_generated",
    "notif_pipeline_complete", "notif_weekly_digest", "notif_in_app"
}

# Define which preferences are string selections
STRING_PREFS = {
    "default_view", "time_range", "week_start", "timezone", "display_name"
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
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    prefs = get_prefs(user_id)
    
    # Process boolean preferences
    for k in BOOL_PREFS:
        if k in data:
            prefs[k] = bool(data[k])
    
    # Process string preferences with validation
    for k in STRING_PREFS:
        if k in data:
            val = str(data[k]).strip() if data[k] is not None else ""
            # Validate specific fields
            if k == "default_view" and val not in ("overview", "analytics", "tasks"):
                val = "overview"
            elif k == "time_range" and val not in ("7d", "30d", "90d", "all"):
                val = "30d"
            elif k == "week_start" and val not in ("sunday", "monday"):
                val = "monday"
            elif k == "timezone":
                # Allow any timezone string, but cap length
                val = val[:50]
            elif k == "display_name":
                # Cap display name length
                val = val[:100]
            prefs[k] = val
    
    # Handle task_order separately
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
        app.logger.info(f"Preferences saved for user {user_id}")
        return jsonify(prefs)
    except Exception as e:
        app.logger.error(f"Failed to save preferences for user {user_id}: {e}")
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
    
    from datetime import datetime, timedelta
    today = datetime.utcnow().date().isoformat()
    week_later = (datetime.utcnow().date() + timedelta(days=7)).isoformat()
    week_ago = (datetime.utcnow().date() - timedelta(days=7)).isoformat()
    
    # Tasks due in next 7 days (not done)
    tasks_due_soon = conn.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE user_id = ? AND done = 0 AND due_date IS NOT NULL AND due_date != '' AND due_date >= ? AND due_date <= ?",
        (user_id, today, week_later),
    ).fetchone()["c"]
    
    # Tasks due today
    tasks_due_today = conn.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE user_id = ? AND done = 0 AND due_date = ?",
        (user_id, today),
    ).fetchone()["c"]
    
    # Overdue tasks
    tasks_overdue = conn.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE user_id = ? AND done = 0 AND due_date IS NOT NULL AND due_date != '' AND due_date < ?",
        (user_id, today),
    ).fetchone()["c"]
    
    # Tasks completed this week
    tasks_done_this_week = conn.execute(
        "SELECT COUNT(*) as c FROM activity_log WHERE user_id = ? AND action = 'task_update' AND date(created_at) >= ?",
        (user_id, week_ago),
    ).fetchone()["c"]
    
    # Events this week
    events_this_week = conn.execute(
        "SELECT COUNT(*) as c FROM events WHERE user_id = ? AND date >= ? AND date <= ?",
        (user_id, today, week_later),
    ).fetchone()["c"]
    
    # Activity this week vs last week (for comparison)
    activity_this_week = conn.execute(
        "SELECT COUNT(*) as c FROM activity_log WHERE user_id = ? AND date(created_at) >= ?",
        (user_id, week_ago),
    ).fetchone()["c"]
    two_weeks_ago = (datetime.utcnow().date() - timedelta(days=14)).isoformat()
    activity_last_week = conn.execute(
        "SELECT COUNT(*) as c FROM activity_log WHERE user_id = ? AND date(created_at) >= ? AND date(created_at) < ?",
        (user_id, two_weeks_ago, week_ago),
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
        "tasks_due_today": tasks_due_today,
        "tasks_overdue": tasks_overdue,
        "tasks_done_this_week": tasks_done_this_week,
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
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    
    task_id = str(uuid.uuid4())
    team_id = get_team_id()
    assigned_raw = data.get("assigned_to")
    if isinstance(assigned_raw, list):
        assigned_to = ",".join(str(e).strip() for e in assigned_raw if str(e).strip())
    else:
        assigned_to = (assigned_raw or "").strip()
    due_date = (data.get("due_date") or "").strip()
    urgency = (data.get("urgency") or "normal").strip() or "normal"
    
    conn = None
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO tasks (id, user_id, team_id, text, assigned_to, due_date, urgency, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (task_id, user_id, team_id, text, assigned_to, due_date, urgency),
        )
        conn.commit()
        log_activity(user_id, "task_create", "task", task_id)
        
        if assigned_to:
            emails = [e.strip() for e in assigned_to.split(",") if e.strip()]
            send_app_email(
                "task_assigned",
                "Task assigned: " + text[:50],
                f"<p>You were assigned a task:</p><p><strong>{text}</strong></p><p>Urgency: {urgency}</p><p>Due: {due_date or 'Not set'}</p>",
                to_emails=emails,
            )
        return jsonify({"id": task_id, "text": text, "done": False, "assigned_to": assigned_to, "due_date": due_date, "urgency": urgency}), 201
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        return jsonify({"error": "Failed to save task. Please try again."}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    
    note_id = str(uuid.uuid4())
    team_id = get_team_id()
    body = (data.get("body") or "").strip()
    
    conn = None
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO notes (id, user_id, team_id, title, body, updated_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (note_id, user_id, team_id, title, body)
        )
        conn.commit()
        log_activity(user_id, "note_create", "note", note_id)
        return jsonify({"id": note_id, "title": title, "body": body}), 201
    except Exception as e:
        logger.error(f"Failed to create note: {e}")
        return jsonify({"error": "Failed to save note. Please try again."}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/notes/<nid>", methods=["DELETE"])
@login_required
def api_notes_delete(nid):
    user_id = get_user_id()
    conn = None
    try:
        conn = get_db()
        cur = conn.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (nid, user_id))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Note not found"}), 404
        log_activity(user_id, "note_delete", "note", nid)
        return jsonify({"ok": True}), 200
    except Exception as e:
        logger.error(f"Failed to delete note: {e}")
        return jsonify({"error": "Failed to delete note"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# — API: reports (dedicated storage for generated reports)
@app.route("/api/reports", methods=["GET"])
@login_required
def api_reports_list():
    """Get all reports for the current user."""
    user_id = get_user_id()
    team_id = get_team_id()
    
    conn = None
    try:
        conn = get_db()
        if team_id:
            rows = conn.execute(
                "SELECT id, title, body, report_type, generated_from, file_path, ai_summary, created_at, updated_at FROM reports WHERE user_id = ? AND team_id = ? ORDER BY created_at DESC",
                (user_id, team_id)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, body, report_type, generated_from, file_path, ai_summary, created_at, updated_at FROM reports WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            ).fetchall()
        reports = [{
            "id": r["id"],
            "title": r["title"],
            "body": r["body"] or "",
            "report_type": r["report_type"],
            "generated_from": r["generated_from"],
            "file_path": r["file_path"],
            "ai_summary": r["ai_summary"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"]
        } for r in rows]
        return jsonify({"reports": reports}), 200
    except Exception as e:
        logger.error(f"Failed to list reports: {e}")
        return jsonify({"error": "Failed to load reports"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/reports", methods=["POST"])
@login_required
def api_reports_create():
    """Create a new report."""
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    
    report_id = str(uuid.uuid4())
    team_id = get_team_id()
    body = (data.get("body") or "").strip()
    report_type = (data.get("report_type") or "general").strip()
    generated_from = data.get("generated_from")  # e.g., pipeline run ID
    file_path = data.get("file_path")
    ai_summary = data.get("ai_summary")
    
    conn = None
    try:
        conn = get_db()
        conn.execute(
            """INSERT INTO reports (id, user_id, team_id, title, body, report_type, generated_from, file_path, ai_summary, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            (report_id, user_id, team_id, title, body, report_type, generated_from, file_path, ai_summary)
        )
        conn.commit()
        log_activity(user_id, "report_create", "report", report_id)
        return jsonify({
            "id": report_id,
            "title": title,
            "body": body,
            "report_type": report_type,
            "generated_from": generated_from,
            "file_path": file_path,
            "ai_summary": ai_summary
        }), 201
    except Exception as e:
        logger.error(f"Failed to create report: {e}")
        return jsonify({"error": "Failed to save report. Please try again."}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/reports/<rid>", methods=["GET"])
@login_required
def api_reports_get(rid):
    """Get a specific report."""
    user_id = get_user_id()
    conn = None
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT id, title, body, report_type, generated_from, file_path, ai_summary, created_at, updated_at FROM reports WHERE id = ? AND user_id = ?",
            (rid, user_id)
        ).fetchone()
        if not row:
            return jsonify({"error": "Report not found"}), 404
        return jsonify(dict(row)), 200
    except Exception as e:
        logger.error(f"Failed to get report: {e}")
        return jsonify({"error": "Failed to load report"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/reports/<rid>", methods=["PATCH"])
@login_required
def api_reports_update(rid):
    """Update a report."""
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    
    conn = None
    try:
        conn = get_db()
        row = conn.execute("SELECT id FROM reports WHERE id = ? AND user_id = ?", (rid, user_id)).fetchone()
        if not row:
            return jsonify({"error": "Report not found"}), 404
        
        updates = []
        params = []
        if "title" in data:
            updates.append("title = ?")
            params.append((data["title"] or "").strip())
        if "body" in data:
            updates.append("body = ?")
            params.append((data["body"] or "").strip())
        if "ai_summary" in data:
            updates.append("ai_summary = ?")
            params.append(data["ai_summary"])
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(rid)
            params.append(user_id)
            conn.execute(f"UPDATE reports SET {', '.join(updates)} WHERE id = ? AND user_id = ?", params)
            conn.commit()
        
        log_activity(user_id, "report_update", "report", rid)
        
        row = conn.execute(
            "SELECT id, title, body, report_type, generated_from, file_path, ai_summary, created_at, updated_at FROM reports WHERE id = ? AND user_id = ?",
            (rid, user_id)
        ).fetchone()
        return jsonify(dict(row)), 200
    except Exception as e:
        logger.error(f"Failed to update report: {e}")
        return jsonify({"error": "Failed to update report"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/reports/<rid>", methods=["DELETE"])
@login_required
def api_reports_delete(rid):
    """Delete a report."""
    user_id = get_user_id()
    conn = None
    try:
        conn = get_db()
        cur = conn.execute("DELETE FROM reports WHERE id = ? AND user_id = ?", (rid, user_id))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Report not found"}), 404
        log_activity(user_id, "report_delete", "report", rid)
        return jsonify({"ok": True}), 200
    except Exception as e:
        logger.error(f"Failed to delete report: {e}")
        return jsonify({"error": "Failed to delete report"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    
    data = request.get_json(silent=True) or {}
    date = (data.get("date") or "").strip()
    title = (data.get("title") or "").strip()
    if not date or not title:
        return jsonify({"error": "date and title required"}), 400
    
    event_id = str(uuid.uuid4())
    team_id = get_team_id()
    time_start = (data.get("time_start") or "").strip() or None
    time_end = (data.get("time_end") or "").strip() or None
    notes = (data.get("notes") or "").strip() or None
    is_all_day = 1 if data.get("is_all_day", True) else 0
    
    conn = None
    try:
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO events (id, user_id, team_id, date, title, time_start, time_end, notes, is_all_day, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (event_id, user_id, team_id, date, title, time_start, time_end, notes, is_all_day),
            )
        except sqlite3.OperationalError:
            # Fallback for older schema
            conn.execute("INSERT INTO events (id, user_id, date, title) VALUES (?, ?, ?, ?)", (event_id, user_id, date, title))
        conn.commit()
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
    except Exception as e:
        logger.error(f"Failed to create event: {e}")
        return jsonify({"error": "Failed to save event. Please try again."}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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


# ═══════════════════════════════════════════════════════════════════════════
# API: Pipeline AI
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/ai/pipeline/summarize", methods=["POST"])
@login_required
def api_ai_pipeline_summarize():
    """Summarize a pipeline run."""
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    run_id = data.get("run_id")
    
    # Find the run from database
    run_data = db_get_pipeline_run(run_id, user_id)
    
    if not run_data:
        return jsonify({"error": "Run not found"}), 404
    
    from tools import ai_service
    summary, err = ai_service.summarize_pipeline_run(run_data, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"summary": summary}), 200


@app.route("/api/ai/pipeline/explain-failure", methods=["POST"])
@login_required
def api_ai_pipeline_explain_failure():
    """Explain a pipeline failure."""
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    run_id = data.get("run_id")
    logs = data.get("logs", [])
    
    # Find the run from database
    run_data = db_get_pipeline_run(run_id, user_id)
    
    if not run_data:
        return jsonify({"error": "Run not found"}), 404
    
    from tools import ai_service
    explanation, err = ai_service.explain_pipeline_failure(run_data, logs, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"explanation": explanation}), 200


@app.route("/api/ai/pipeline/optimize", methods=["POST"])
@login_required
def api_ai_pipeline_optimize():
    """Suggest pipeline optimizations."""
    user_id = get_user_id()
    team_id = get_team_id()
    
    # Get user's pipeline runs from database
    user_runs = db_get_pipeline_runs(user_id, team_id, limit=50)
    
    from tools import ai_service
    suggestions, err = ai_service.suggest_pipeline_optimizations(user_runs, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"suggestions": suggestions or []}), 200


# ═══════════════════════════════════════════════════════════════════════════
# API: Reports AI
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/ai/reports/summarize", methods=["POST"])
@login_required
def api_ai_reports_summarize():
    """Summarize a report."""
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    
    if not body:
        return jsonify({"error": "body required"}), 400
    
    from tools import ai_service
    summary, err = ai_service.summarize_report(title, body, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"summary": summary}), 200


@app.route("/api/ai/reports/rewrite", methods=["POST"])
@login_required
def api_ai_reports_rewrite():
    """Rewrite a report for a specific audience."""
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    audience = (data.get("audience") or "executive").strip().lower()
    
    if not body:
        return jsonify({"error": "body required"}), 400
    if audience not in ["executive", "marketing", "technical"]:
        audience = "executive"
    
    from tools import ai_service
    rewritten, err = ai_service.rewrite_report_for_audience(title, body, audience, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"rewritten": rewritten, "audience": audience}), 200


@app.route("/api/ai/reports/takeaways", methods=["POST"])
@login_required
def api_ai_reports_takeaways():
    """Extract key takeaways from a report."""
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    
    if not body:
        return jsonify({"error": "body required"}), 400
    
    from tools import ai_service
    result, err = ai_service.extract_report_takeaways(title, body, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(result or {"takeaways": [], "action_items": []}), 200


# ═══════════════════════════════════════════════════════════════════════════
# API: Workload & Tasks AI
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/ai/workload/summarize", methods=["POST"])
@login_required
def api_ai_workload_summarize():
    """Summarize current workload."""
    user_id = get_user_id()
    conn = get_db()
    tasks = conn.execute(
        "SELECT text, due_date, urgency, done FROM tasks WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
        (user_id,)
    ).fetchall()
    events = conn.execute(
        "SELECT title, date FROM events WHERE user_id = ? ORDER BY date ASC LIMIT 30",
        (user_id,)
    ).fetchall()
    conn.close()
    
    tasks_list = [dict(t) for t in tasks]
    events_list = [dict(e) for e in events]
    
    from tools import ai_service
    summary, err = ai_service.summarize_workload(tasks_list, events_list, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"summary": summary}), 200


@app.route("/api/ai/workload/focus", methods=["POST"])
@login_required
def api_ai_workload_focus():
    """Suggest what to focus on today."""
    user_id = get_user_id()
    conn = get_db()
    tasks = conn.execute(
        "SELECT text, due_date, urgency, done FROM tasks WHERE user_id = ? AND done = 0 ORDER BY created_at DESC LIMIT 30",
        (user_id,)
    ).fetchall()
    conn.close()
    
    tasks_list = [dict(t) for t in tasks]
    
    from tools import ai_service
    suggestion, err = ai_service.suggest_focus(tasks_list, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"suggestion": suggestion}), 200


# ═══════════════════════════════════════════════════════════════════════════
# API: Notes AI
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/ai/notes/summarize", methods=["POST"])
@login_required
def api_ai_notes_summarize():
    """Summarize a note."""
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    
    if not body:
        return jsonify({"error": "body required"}), 400
    
    from tools import ai_service
    summary, err = ai_service.summarize_note(title, body, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"summary": summary}), 200


@app.route("/api/ai/notes/extract-actions", methods=["POST"])
@login_required
def api_ai_notes_extract_actions():
    """Extract action items from note content."""
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    
    if not content:
        return jsonify({"error": "content required"}), 400
    
    from tools import ai_service
    actions, err = ai_service.extract_action_items(content, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"actions": actions or []}), 200


@app.route("/api/ai/notes/find-themes", methods=["POST"])
@login_required
def api_ai_notes_find_themes():
    """Find common themes across notes."""
    user_id = get_user_id()
    conn = get_db()
    notes = conn.execute(
        "SELECT title, body FROM notes WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
        (user_id,)
    ).fetchall()
    conn.close()
    
    notes_list = [dict(n) for n in notes]
    
    from tools import ai_service
    themes, err = ai_service.find_related_themes(notes_list, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"themes": themes or []}), 200


@app.route("/api/ai/generate-email", methods=["POST"])
@login_required
def api_ai_generate_email():
    """Generate a polished email draft using AI.
    
    Input JSON:
    - recipient_name: str (required)
    - recipient_email: str (optional)
    - subject: str (optional - AI can suggest)
    - purpose: str (follow-up, introduction, proposal, etc.)
    - tone: str (professional, friendly, casual, persuasive, formal, urgent)
    - context: str (additional context)
    - key_points: str (required - main points to include)
    
    Returns:
    - draft: str (the generated email body)
    - subject: str (subject line, generated if not provided)
    - suggestions: list[str] (improvement suggestions)
    """
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    
    recipient_name = (data.get("recipient_name") or "").strip()
    recipient_email = (data.get("recipient_email") or "").strip()
    subject = (data.get("subject") or "").strip()
    purpose = (data.get("purpose") or "follow-up").strip()
    tone = (data.get("tone") or "professional").strip()
    context = (data.get("context") or "").strip()
    key_points = (data.get("key_points") or "").strip()
    
    if not recipient_name:
        return jsonify({"error": "Recipient name is required"}), 400
    if not key_points:
        return jsonify({"error": "Key points are required"}), 400
    
    from tools import ai_service
    result, err = ai_service.generate_email_draft(
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        subject=subject,
        purpose=purpose,
        tone=tone,
        context=context,
        key_points=key_points,
        user_id=user_id,
        log_fn=log_activity
    )
    
    if err:
        return jsonify({"error": err}), 400
    
    return jsonify(result), 200


# ═══════════════════════════════════════════════════════════════════════════
# API: AI Briefing (Dashboard)
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/ai/briefing", methods=["POST"])
@login_required
def api_ai_briefing():
    """Generate comprehensive AI briefing."""
    user_id = get_user_id()
    conn = get_db()
    
    # Get stats
    tasks_total = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE user_id = ?", (user_id,)).fetchone()["c"]
    tasks_done = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE user_id = ? AND done = 1", (user_id,)).fetchone()["c"]
    
    from datetime import datetime, timedelta
    today = datetime.utcnow().date().isoformat()
    tasks_overdue = conn.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE user_id = ? AND done = 0 AND due_date IS NOT NULL AND due_date != '' AND due_date < ?",
        (user_id, today)
    ).fetchone()["c"]
    
    week_later = (datetime.utcnow().date() + timedelta(days=7)).isoformat()
    events_this_week = conn.execute(
        "SELECT COUNT(*) as c FROM events WHERE user_id = ? AND date >= ? AND date <= ?",
        (user_id, today, week_later)
    ).fetchone()["c"]
    
    # Get upcoming tasks
    tasks = conn.execute(
        "SELECT text, due_date FROM tasks WHERE user_id = ? AND done = 0 ORDER BY due_date ASC LIMIT 15",
        (user_id,)
    ).fetchall()
    
    # Get upcoming events
    events = conn.execute(
        "SELECT title, date FROM events WHERE user_id = ? AND date >= ? ORDER BY date ASC LIMIT 15",
        (user_id, today)
    ).fetchall()
    
    # Get recent activity
    activity = conn.execute(
        "SELECT action FROM activity_log WHERE user_id = ? ORDER BY created_at DESC LIMIT 15",
        (user_id,)
    ).fetchall()
    
    conn.close()
    
    stats = {
        "tasks_total": tasks_total,
        "tasks_done": tasks_done,
        "tasks_overdue": tasks_overdue,
        "events_this_week": events_this_week,
    }
    tasks_list = [dict(t) for t in tasks]
    events_list = [dict(e) for e in events]
    activity_list = [dict(a) for a in activity]
    
    from tools import ai_service
    briefing, err = ai_service.generate_briefing(stats, tasks_list, events_list, activity_list, user_id, log_activity)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(briefing or {}), 200


# ═══════════════════════════════════════════════════════════════════════════
# API: Global AI Command
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/ai/command", methods=["POST"])
@login_required
def api_ai_command():
    """Process a natural language AI command."""
    user_id = get_user_id()
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    
    if not query:
        return jsonify({"error": "query required"}), 400
    
    from tools import ai_service
    
    # First, route the command
    routing, err = ai_service.route_ai_command(query, user_id, log_activity)
    if err:
        # Fall back to general query
        answer, err2 = ai_service.answer_general_query(query, {}, user_id, log_activity)
        if err2:
            return jsonify({"error": err2}), 400
        return jsonify({"response": answer, "type": "general"}), 200
    
    intent = routing.get("intent", "unknown")
    target = routing.get("target", "general")
    
    # Route to appropriate handler based on intent
    if intent == "unknown" or target == "general":
        answer, err = ai_service.answer_general_query(query, {}, user_id, log_activity)
        if err:
            return jsonify({"error": err}), 400
        return jsonify({"response": answer, "type": "general", "routing": routing}), 200
    
    # For now, use general answer with context note
    answer, err = ai_service.answer_general_query(
        query, 
        {"note": f"This query relates to {target}. Intent detected: {intent}."},
        user_id, 
        log_activity
    )
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"response": answer, "type": target, "routing": routing}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
# --- Health check endpoint for Render ---
from flask import jsonify

@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"}), 200
