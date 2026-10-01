import os
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash


# ============================================================
# Environment / logging
# ============================================================

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("learnsense-api")


def required_env(name: str) -> str:
    """Read a required environment variable."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


# ============================================================
# Flask app
# ============================================================

app = Flask(__name__)

# Maximum JSON/request body size.
# Increase this only if you intentionally need larger submissions.
app.config["MAX_CONTENT_LENGTH"] = int(
    os.getenv("MAX_CONTENT_LENGTH", str(2 * 1024 * 1024))
)

# Production should use PostgreSQL. SQLite remains available only as a
# development fallback when DATABASE_URL is not supplied.
database_url = os.getenv("DATABASE_URL", "sqlite:///learnsense.db")

# Some hosting providers still return postgres:// URLs.
if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql+psycopg://",
        1,
    )
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )

# Security configuration.
jwt_secret = os.getenv("JWT_SECRET_KEY")
if not jwt_secret:
    raise RuntimeError(
        "JWT_SECRET_KEY is required. Set a strong random value in production."
    )
if os.getenv("FLASK_ENV", "production") == "production" and len(jwt_secret) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY must contain at least 32 characters in production."
    )

app.config.update(
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    JWT_SECRET_KEY=jwt_secret,
    JWT_ACCESS_TOKEN_EXPIRES=timedelta(
        minutes=int(os.getenv("JWT_ACCESS_MINUTES", "30"))
    ),
    JWT_REFRESH_TOKEN_EXPIRES=timedelta(
        days=int(os.getenv("JWT_REFRESH_DAYS", "30"))
    ),
    JWT_TOKEN_LOCATION=["headers"],
    JWT_HEADER_NAME="Authorization",
    JWT_HEADER_TYPE="Bearer",
)

# Explicitly keep debug disabled unless you deliberately enable it locally.
app.config["DEBUG"] = os.getenv("FLASK_DEBUG", "0") == "1"


# ============================================================
# Extensions
# ============================================================

db = SQLAlchemy(app)
migrate = Migrate(app, db)
jwt = JWTManager(app)

# Rate limiting.
# For multiple production instances, configure a shared storage backend
# such as Redis using RATELIMIT_STORAGE_URI.
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
)


# ============================================================
# CORS
# ============================================================

dashboard_origin = os.getenv("DASHBOARD_ORIGIN")

if not dashboard_origin:
    # Do not silently allow every website in production.
    # Local development can explicitly set DASHBOARD_ORIGIN=http://localhost:5000
    if os.getenv("FLASK_ENV", "production") == "production":
        raise RuntimeError(
            "DASHBOARD_ORIGIN is required in production."
        )
    dashboard_origin = "http://localhost:3000"

dashboard_origin = dashboard_origin.rstrip("/")
parsed_dashboard_origin = urlparse(dashboard_origin)
if (
    parsed_dashboard_origin.scheme not in {"http", "https"}
    or not parsed_dashboard_origin.netloc
    or parsed_dashboard_origin.path not in {"", "/"}
):
    raise RuntimeError(
        "DASHBOARD_ORIGIN must be an origin such as https://dashboard.example.com"
    )

# Allow both the dashboard origin and Chrome/Brave extension origins.
# Chrome extensions send requests with Origin: chrome-extension://<id>.
import re
_allowed_origins = [dashboard_origin]

@app.after_request
def handle_cors_for_extensions(response):
    """Allow Chrome extension origins for /api/* routes."""
    origin = request.headers.get("Origin", "")
    if (
        request.path.startswith("/api/")
        and re.match(r"^chrome-extension://[a-z0-9]{32}$", origin)
    ):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization"
        )
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        )
        response.headers.add("Vary", "Origin")
    return response

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": _allowed_origins,
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
        }
    },
)


# ============================================================
# Dashboard static files
# ============================================================

DASHBOARD_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "dashboard")
)


@app.get("/dashboard")
@app.get("/dashboard/")
def dashboard_home():
    return send_from_directory(DASHBOARD_DIR, "index.html")


@app.get("/dashboard/<path:filename>")
def dashboard_files(filename):
    return send_from_directory(DASHBOARD_DIR, filename)


# ============================================================
# Security headers
# ============================================================

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Only enable HSTS when the public API is definitely HTTPS.
    if os.getenv("ENABLE_HSTS", "0") == "1":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response


# ============================================================
# Error handlers
# ============================================================

@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return jsonify({"error": "Request body is too large."}), 413


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Endpoint not found."}), 404
    return _error


@app.errorhandler(500)
def internal_error(error):
    # Roll back a failed DB transaction so the session is usable again.
    db.session.rollback()
    logger.exception("Unhandled server error: %s", error)
    return jsonify({"error": "Internal server error."}), 500


# ============================================================
# Database models
# ============================================================

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=True)

    # Kept simple for compatibility with the existing database design.
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Problem(db.Model):
    __tablename__ = "problems"

    id = db.Column(db.Integer, primary_key=True)
    leetcode_id = db.Column(db.Integer, nullable=True)
    title = db.Column(db.String(500), nullable=False)
    slug = db.Column(
        db.String(500),
        unique=True,
        nullable=False,
        index=True,
    )
    url = db.Column(db.Text, nullable=False)


class Submission(db.Model):
    """
    Successful submissions are stored remotely.

    Attempt counters are calculated by the extension at the moment the
    Accepted submission is recorded.
    """

    __tablename__ = "submissions"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    problem_id = db.Column(
        db.Integer,
        db.ForeignKey("problems.id"),
        nullable=False,
        index=True,
    )

    code = db.Column(db.Text, nullable=False, default="")
    language = db.Column(
        db.String(80),
        nullable=False,
        default="unknown",
    )
    verdict = db.Column(
        db.String(100),
        nullable=False,
        default="Accepted",
    )

    right_attempts = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )
    wrong_attempts = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )
    total_attempts = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    submitted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = db.relationship(
        "User",
        backref=db.backref("submissions", lazy=True),
    )

    problem = db.relationship(
        "Problem",
        backref=db.backref("submissions", lazy=True),
    )

    __table_args__ = (
        Index(
            "ix_submissions_user_problem_submitted",
            "user_id",
            "problem_id",
            "submitted_at",
        ),
    )


class DashboardCode(db.Model):
    """
    Short-lived, one-time extension -> dashboard handoff code.

    The raw code is never stored. Only its SHA-256 hash is stored.
    """

    __tablename__ = "dashboard_codes"

    id = db.Column(db.Integer, primary_key=True)

    code_hash = db.Column(
        db.String(128),
        unique=True,
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    expires_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
    )

    used_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )


# ============================================================
# Create tables (safe on existing databases — only adds missing)
# ============================================================

with app.app_context():
    db.create_all()


# ============================================================
# JWT callbacks
# ============================================================

@jwt.unauthorized_loader
def jwt_missing_token(message):
    return jsonify({"error": "Authentication required."}), 401


@jwt.invalid_token_loader
def jwt_invalid_token(message):
    return jsonify({"error": "Invalid authentication token."}), 401


@jwt.expired_token_loader
def jwt_expired_token(jwt_header, jwt_payload):
    return jsonify({"error": "Authentication token has expired."}), 401


# ============================================================
# Helpers
# ============================================================

def now_utc():
    return datetime.now(timezone.utc)


def user_id_from_token():
    return int(get_jwt_identity())


def user_json(user):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
    }


def parse_timestamp(value):
    """
    Accept a JavaScript-style Unix timestamp in milliseconds.
    If missing/invalid, use the server's current UTC time.
    """
    try:
        timestamp = float(value) / 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return now_utc()


def hash_code(code):
    return hashlib.sha256(
        code.encode("utf-8")
    ).hexdigest()


def valid_http_url(value):
    """
    Basic URL validation.

    For this project, only HTTPS URLs are accepted in production.
    Local HTTP can be allowed during development.
    """
    try:
        parsed = urlparse(value)

        if parsed.scheme == "https" and parsed.netloc:
            return True

        if (
            os.getenv("FLASK_ENV", "production") != "production"
            and parsed.scheme == "http"
            and parsed.netloc
        ):
            return True

    except ValueError:
        pass

    return False


def clean_string(value, max_length):
    if value is None:
        return ""
    return str(value).strip()[:max_length]


# ============================================================
# Health
# ============================================================

@app.get("/api/health")
def health():
    try:
        db.session.execute(db.text("SELECT 1"))

        return jsonify({
            "ok": True,
            "service": "LearnSense API",
            "database": "connected",
        })

    except Exception:
        logger.exception("Health check database failure")
        return jsonify({
            "ok": False,
            "service": "LearnSense API",
            "database": "unavailable",
        }), 503


# ============================================================
# Authentication
# ============================================================

@app.post("/api/auth/register")
@limiter.limit("5 per hour")
def register():
    data = request.get_json(silent=True) or {}

    email = clean_string(data.get("email"), 255).lower()
    password = str(data.get("password", ""))
    name = clean_string(data.get("name"), 120) or None

    if not email or not password:
        return jsonify({
            "error": "Email and password are required."
        }), 400

    if len(email) > 255 or "@" not in email:
        return jsonify({
            "error": "A valid email address is required."
        }), 400

    if len(password) < 8:
        return jsonify({
            "error": "Password must be at least 8 characters."
        }), 400

    if len(password) > 256:
        return jsonify({
            "error": "Password is too long."
        }), 400

    if User.query.filter_by(email=email).first():
        return jsonify({
            "error": "An account with this email already exists."
        }), 409

    user = User(
        email=email,
        name=name,
        password_hash=generate_password_hash(password),
    )

    db.session.add(user)
    db.session.commit()

    access_token = create_access_token(
        identity=str(user.id)
    )

    refresh_token = create_refresh_token(
        identity=str(user.id)
    )

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user_json(user),
    }), 201


@app.post("/api/auth/login")
@limiter.limit("10 per minute")
def login():
    data = request.get_json(silent=True) or {}

    email = clean_string(data.get("email"), 255).lower()
    password = str(data.get("password", ""))

    user = User.query.filter_by(email=email).first()

    if not user or not check_password_hash(
        user.password_hash,
        password,
    ):
        return jsonify({
            "error": "Invalid email or password."
        }), 401

    access_token = create_access_token(
        identity=str(user.id)
    )

    refresh_token = create_refresh_token(
        identity=str(user.id)
    )

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user_json(user),
    })


@app.post("/api/auth/refresh")
@jwt_required(refresh=True)
@limiter.limit("30 per hour")
def refresh():
    user_id = user_id_from_token()

    user = db.session.get(User, user_id)

    if not user:
        return jsonify({
            "error": "User not found."
        }), 404

    access_token = create_access_token(
        identity=str(user.id)
    )

    return jsonify({
        "access_token": access_token
    })


@app.get("/api/me")
@jwt_required()
def me():
    user = db.session.get(
        User,
        user_id_from_token(),
    )

    if not user:
        return jsonify({
            "error": "User not found."
        }), 404

    return jsonify(user_json(user))


# ============================================================
# Dashboard authentication handoff
# ============================================================

@app.post("/api/auth/dashboard-code")
@jwt_required()
@limiter.limit("10 per minute")
def create_dashboard_code():
    """
    Create a short-lived one-use code for opening the dashboard.

    Never place a JWT in the dashboard URL.
    """

    raw = secrets.token_urlsafe(32)

    record = DashboardCode(
        code_hash=hash_code(raw),
        user_id=user_id_from_token(),
        expires_at=now_utc() + timedelta(minutes=2),
    )

    db.session.add(record)
    db.session.commit()

    dashboard_url = os.getenv("DASHBOARD_URL")
    if not dashboard_url:
        dashboard_url = (
            "http://localhost:3000"
            if os.getenv("FLASK_ENV", "production") != "production"
            else ""
        )
    dashboard_url = dashboard_url.rstrip("/")
    parsed_dashboard_url = urlparse(dashboard_url)
    if (
        parsed_dashboard_url.scheme not in {"http", "https"}
        or not parsed_dashboard_url.netloc
        or parsed_dashboard_url.path not in {"", "/"}
    ):
        return jsonify({
            "error": "Dashboard is not configured correctly."
        }), 503

    return jsonify({
        "url": (
            f"{dashboard_url}/extension-login.html"
            f"?code={raw}"
        )
    })


@app.post("/api/auth/exchange-dashboard-code")
@limiter.limit("20 per minute")
def exchange_dashboard_code():
    data = request.get_json(silent=True) or {}

    raw = clean_string(data.get("code"), 512)

    if not raw:
        return jsonify({
            "error": "Code is required."
        }), 400

    record = DashboardCode.query.filter_by(
        code_hash=hash_code(raw)
    ).first()

    if (
        not record
        or record.used_at is not None
        or record.expires_at < now_utc()
    ):
        return jsonify({
            "error": "Dashboard code is invalid or expired."
        }), 401

    # Mark it used BEFORE issuing the token.
    record.used_at = now_utc()
    db.session.commit()

    access_token = create_access_token(
        identity=str(record.user_id)
    )

    refresh_token = create_refresh_token(
        identity=str(record.user_id)
    )

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
    })


# ============================================================
# Submission API
# ============================================================

@app.post("/api/submissions")
@jwt_required()
@limiter.limit("120 per hour")
def create_submission():
    """
    Accept only successful submissions.

    The extension sends the counters calculated from the user's activity on
    a supported coding platform.
    """

    data = request.get_json(silent=True) or {}

    verdict = clean_string(data.get("verdict"), 100)

    if verdict != "Accepted":
        return jsonify({
            "error": "Only Accepted submissions are stored remotely."
        }), 400

    title = clean_string(
        data.get("title"),
        500,
    ) or "Untitled problem"

    slug = clean_string(
        data.get("problemSlug"),
        500,
    )

    url = clean_string(
        data.get("problemUrl"),
        2000,
    )

    code = str(data.get("code", ""))

    language = (
        clean_string(
            data.get("lang", "unknown"),
            80,
        )
        or "unknown"
    )

    if not slug or not url:
        return jsonify({
            "error": "problemSlug and problemUrl are required."
        }), 400

    if len(code.encode("utf-8")) > 1_500_000:
        return jsonify({
            "error": "Submitted code is too large."
        }), 413

    if not valid_http_url(url):
        return jsonify({
            "error": "problemUrl must be a valid HTTPS URL."
        }), 400

    try:
        right_attempts = max(
            1,
            int(data.get("rightAttempts", 1)),
        )

        wrong_attempts = max(
            0,
            int(data.get("wrongAttempts", 0)),
        )

        total_attempts = max(
            1,
            int(
                data.get(
                    "totalAttempts",
                    right_attempts + wrong_attempts,
                )
            ),
        )

    except (ValueError, TypeError):
        return jsonify({
            "error": "Attempt counters must be integers."
        }), 400

    # Prevent unreasonable counters.
    if (
        right_attempts > 100000
        or wrong_attempts > 100000
        or total_attempts > 100000
    ):
        return jsonify({
            "error": "Attempt counters are out of range."
        }), 400

    if total_attempts != right_attempts + wrong_attempts:
        return jsonify({
            "error": (
                "totalAttempts must equal "
                "rightAttempts + wrongAttempts."
            )
        }), 400

    problem = Problem.query.filter_by(
        slug=slug
    ).first()

    if not problem:
        problem = Problem(
            title=title,
            slug=slug,
            url=url,
        )

        db.session.add(problem)
        db.session.flush()

    else:
        # Keep the problem metadata current.
        problem.title = title
        problem.url = url

    submission = Submission(
        user_id=user_id_from_token(),
        problem_id=problem.id,
        code=code,
        language=language,
        verdict="Accepted",
        right_attempts=right_attempts,
        wrong_attempts=wrong_attempts,
        total_attempts=total_attempts,
        submitted_at=parse_timestamp(
            data.get("timestamp")
        ),
    )

    db.session.add(submission)
    db.session.commit()

    return jsonify({
        "success": True,
        "submission": {
            "id": submission.id,
            "problem": problem.title,
            "right_attempts": right_attempts,
            "wrong_attempts": wrong_attempts,
            "total_attempts": total_attempts,
        },
    }), 201


# ============================================================
# Dashboard statistics
# ============================================================

def latest_successes_for_user(user_id):
    rows = (
        Submission.query
        .filter_by(user_id=user_id)
        .order_by(Submission.submitted_at.desc())
        .all()
    )

    latest = {}

    for row in rows:
        if row.problem_id not in latest:
            latest[row.problem_id] = row

    return list(latest.values())


@app.get("/api/dashboard/summary")
@jwt_required()
def dashboard_summary():
    latest = latest_successes_for_user(
        user_id_from_token()
    )

    right = sum(
        s.right_attempts
        for s in latest
    )

    wrong = sum(
        s.wrong_attempts
        for s in latest
    )

    total = sum(
        s.total_attempts
        for s in latest
    )

    problems = []

    for submission in latest:
        accuracy = (
            round(
                submission.right_attempts
                / submission.total_attempts
                * 100
            )
            if submission.total_attempts
            else 0
        )

        problems.append({
            "id": submission.problem.id,
            "title": submission.problem.title,
            "slug": submission.problem.slug,
            "url": submission.problem.url,
            "correct": submission.right_attempts,
            "wrong": submission.wrong_attempts,
            "attempts": submission.total_attempts,
            "accuracy": accuracy,
            "last_solved_at": (
                submission.submitted_at.isoformat()
            ),
        })

    problems.sort(
        key=lambda item: item["last_solved_at"],
        reverse=True,
    )

    overall_accuracy = (
        round(right / total * 100)
        if total
        else 0
    )

    return jsonify({
        "overall": {
            "solved_problems": len(latest),
            "correct": right,
            "wrong": wrong,
            "total": total,
            "accuracy": overall_accuracy,
        },
        "problems": problems,
    })


# ============================================================
# Problem detail
# ============================================================

@app.get("/api/problems/<slug>")
@jwt_required()
def problem_detail(slug):
    slug = clean_string(slug, 500)

    user_id = user_id_from_token()

    problem = Problem.query.filter_by(
        slug=slug
    ).first()

    if not problem:
        return jsonify({
            "error": "Problem not found."
        }), 404

    submissions = (
        Submission.query
        .filter_by(
            user_id=user_id,
            problem_id=problem.id,
        )
        .order_by(
            Submission.submitted_at.desc()
        )
        .all()
    )

    if not submissions:
        return jsonify({
            "error": "No successful submission for this problem."
        }), 404

    latest = submissions[0]

    accuracy = (
        round(
            latest.right_attempts
            / latest.total_attempts
            * 100
        )
        if latest.total_attempts
        else 0
    )

    return jsonify({
        "problem": {
            "id": problem.id,
            "title": problem.title,
            "slug": problem.slug,
            "url": problem.url,
        },
        "stats": {
            "attempts": latest.total_attempts,
            "correct": latest.right_attempts,
            "wrong": latest.wrong_attempts,
            "accuracy": accuracy,
        },
        "submissions": [
            {
                "id": s.id,
                "verdict": s.verdict,
                "language": s.language,
                "submitted_at": (
                    s.submitted_at.isoformat()
                ),
                "code": s.code,
                "right_attempts": s.right_attempts,
                "wrong_attempts": s.wrong_attempts,
                "total_attempts": s.total_attempts,
            }
            for s in submissions
        ],
    })


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    # Development only.
    # Production should use Gunicorn/uWSGI/etc.
    port = int(os.getenv("PORT", "5000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
