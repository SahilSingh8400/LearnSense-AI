import hashlib
import logging
import os
import re
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
    get_jwt_identity,
    jwt_required,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer, joinedload
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash


# Environment / logging

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("learnsense-api")


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


# FLASK_ENV was removed in Flask 2.3, so APP_ENV is the primary switch now.
# FLASK_ENV is still honoured as a fallback for existing deployments.
APP_ENV = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "production"))
IS_PROD = APP_ENV == "production"


# Flask app

app = Flask(__name__)

if os.getenv("TRUST_PROXY", "0") == "1":
    # Needed behind Nginx/Render/Heroku etc., otherwise every client shares
    # the proxy's IP and the rate limiter blocks everybody together.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.config["MAX_CONTENT_LENGTH"] = int(
    os.getenv("MAX_CONTENT_LENGTH", str(2 * 1024 * 1024))
)

database_url = os.getenv("DATABASE_URL", "sqlite:///learnsense.db")
# NOTE: "+psycopg" requires psycopg v3 (pip install "psycopg[binary]").
# For psycopg2 use "postgresql+psycopg2://" instead.
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

jwt_secret = required_env("JWT_SECRET_KEY")
if IS_PROD and len(jwt_secret) < 32:
    raise RuntimeError("JWT_SECRET_KEY must contain at least 32 characters in production.")

app.config.update(
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    JWT_SECRET_KEY=jwt_secret,
    JWT_ACCESS_TOKEN_EXPIRES=timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "30"))),
    JWT_REFRESH_TOKEN_EXPIRES=timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "30"))),
    JWT_TOKEN_LOCATION=["headers"],
    JWT_HEADER_NAME="Authorization",
    JWT_HEADER_TYPE="Bearer",
    DEBUG=os.getenv("FLASK_DEBUG", "0") == "1",
)


# Extensions

db = SQLAlchemy(app)
migrate = Migrate(app, db)
jwt = JWTManager(app)

# With several workers/instances use a shared store (Redis) via
# RATELIMIT_STORAGE_URI, otherwise each worker keeps its own counters.
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
)


# CORS

def parse_origin(value: str, env_name: str) -> str:
    value = value.rstrip("/")
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path not in {"", "/"}
    ):
        raise RuntimeError(
            f"{env_name} must be an origin such as https://dashboard.example.com"
        )
    return value


dashboard_origin = os.getenv("DASHBOARD_ORIGIN")
if not dashboard_origin:
    if IS_PROD:
        raise RuntimeError("DASHBOARD_ORIGIN is required in production.")
    dashboard_origin = "http://localhost:3000"
dashboard_origin = parse_origin(dashboard_origin, "DASHBOARD_ORIGIN")

# One source of truth: DASHBOARD_URL falls back to DASHBOARD_ORIGIN.
dashboard_url = parse_origin(
    os.getenv("DASHBOARD_URL") or dashboard_origin, "DASHBOARD_URL"
)

# Comma-separated list of YOUR extension IDs. Without an allow-list, any
# installed extension could call the API (login/register brute force etc.).
EXTENSION_IDS = {
    x.strip() for x in os.getenv("EXTENSION_IDS", "").split(",") if x.strip()
}
if IS_PROD and not EXTENSION_IDS:
    logger.warning("EXTENSION_IDS is empty: no Chrome extension will be allowed by CORS.")

EXTENSION_ORIGIN_RE = re.compile(r"^chrome-extension://([a-p]{32})$")

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [dashboard_origin],
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
        }
    },
)


@app.after_request
def handle_cors_for_extensions(response):
    origin = request.headers.get("Origin", "")
    match = EXTENSION_ORIGIN_RE.match(origin)
    if request.path.startswith("/api/") and match:
        ext_id = match.group(1)
        if ext_id in EXTENSION_IDS or (not IS_PROD and not EXTENSION_IDS):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )
            response.headers.add("Vary", "Origin")
    return response


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


# Security headers

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # API responses contain tokens / user code: never let caches keep them.
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"

    if os.getenv("ENABLE_HSTS", "0") == "1":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


# Error handlers

@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return jsonify({"error": "Request body is too large."}), 413


@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Endpoint not found."}), 404
    return error


@app.errorhandler(405)
def method_not_allowed(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Method not allowed."}), 405
    return error


@app.errorhandler(429)
def rate_limited(_error):
    return jsonify({"error": "Too many requests. Please slow down."}), 429


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    logger.exception("Unhandled server error: %s", error)
    return jsonify({"error": "Internal server error."}), 500


# Database models

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=True)
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
    slug = db.Column(db.String(500), unique=True, nullable=False, index=True)
    url = db.Column(db.Text, nullable=False)


class Submission(db.Model):
    __tablename__ = "submissions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    problem_id = db.Column(db.Integer, db.ForeignKey("problems.id"), nullable=False, index=True)

    code = db.Column(db.Text, nullable=False, default="")
    language = db.Column(db.String(80), nullable=False, default="unknown")
    verdict = db.Column(db.String(100), nullable=False, default="Accepted")

    right_attempts = db.Column(db.Integer, nullable=False, default=1)
    wrong_attempts = db.Column(db.Integer, nullable=False, default=0)
    total_attempts = db.Column(db.Integer, nullable=False, default=1)

    submitted_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = db.relationship("User", backref=db.backref("submissions", lazy=True))
    problem = db.relationship("Problem", backref=db.backref("submissions", lazy=True))

    __table_args__ = (
        Index(
            "ix_submissions_user_problem_submitted",
            "user_id",
            "problem_id",
            "submitted_at",
        ),
    )


class DashboardCode(db.Model):
    """Short-lived, one-time extension -> dashboard handoff code (hash only)."""

    __tablename__ = "dashboard_codes"

    id = db.Column(db.Integer, primary_key=True)
    code_hash = db.Column(db.String(128), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)


# Create tables
# When using Flask-Migrate, schema changes must go through `flask db upgrade`.
# create_all() at import time races between Gunicorn workers and bypasses
# migrations, so it's only enabled by default for local development.

if os.getenv("AUTO_CREATE_TABLES", "0" if IS_PROD else "1") == "1":
    with app.app_context():
        db.create_all()


# JWT callbacks

@jwt.unauthorized_loader
def jwt_missing_token(_message):
    return jsonify({"error": "Authentication required."}), 401


@jwt.invalid_token_loader
def jwt_invalid_token(_message):
    return jsonify({"error": "Invalid authentication token."}), 401


@jwt.expired_token_loader
def jwt_expired_token(_header, _payload):
    return jsonify({"error": "Authentication token has expired."}), 401


# Helpers

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,199}$")
LEETCODE_HOSTS = {"leetcode.com", "www.leetcode.com", "leetcode.cn", "www.leetcode.cn"}
MAX_ATTEMPTS = 100_000
MAX_CODE_BYTES = 1_500_000

# Used to keep login timing identical for unknown emails.
DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-password")


class ValidationError(ValueError):
    pass


def now_utc():
    return datetime.now(timezone.utc)


def as_utc(dt):
    """SQLite returns naive datetimes even for timezone=True columns."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def json_body():
    """Always returns a dict (a JSON list/string/null body used to crash with 500)."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def user_id_from_token():
    return int(get_jwt_identity())


def current_user():
    return db.session.get(User, user_id_from_token())


def user_json(user):
    return {"id": user.id, "email": user.email, "name": user.name}


def clean_string(value, max_length):
    """Only real strings are accepted; NUL bytes are removed (PostgreSQL rejects them)."""
    if not isinstance(value, str):
        return ""
    return value.replace("\x00", "").strip()[:max_length]


def hash_code(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def parse_timestamp(value):
    """JS millisecond timestamp. Missing -> now. Invalid/absurd -> error."""
    if value is None:
        return now_utc()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("timestamp must be a number in milliseconds.")
    try:
        dt = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        raise ValidationError("timestamp is out of range.")
    if dt > now_utc() + timedelta(minutes=5) or dt.year < 2010:
        raise ValidationError("timestamp is out of range.")
    return dt


def parse_counter(value, name, minimum):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{name} must be an integer.")
    if value < minimum or value > MAX_ATTEMPTS:
        raise ValidationError(f"{name} must be between {minimum} and {MAX_ATTEMPTS}.")
    return value


def validate_problem_url(url, slug):
    """Only real LeetCode problem pages whose path matches the slug."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    allowed_schemes = {"https"} if IS_PROD else {"https", "http"}
    return (
        parsed.scheme in allowed_schemes
        and (parsed.hostname or "").lower() in LEETCODE_HOSTS
        and parsed.path.startswith(f"/problems/{slug}")
    )


def accuracy_of(right, total):
    return round(right / total * 100) if total else 0


def issue_tokens(user_id):
    return {
        "access_token": create_access_token(identity=str(user_id)),
        "refresh_token": create_refresh_token(identity=str(user_id)),
    }


def login_email_key():
    """Second rate-limit bucket per target account (stops distributed guessing)."""
    return clean_string(json_body().get("email"), 255).lower() or get_remote_address()


# Health

@app.get("/api/health")
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"ok": True, "service": "LearnSense API", "database": "connected"})
    except Exception:
        logger.exception("Health check database failure")
        return jsonify({"ok": False, "service": "LearnSense API", "database": "unavailable"}), 503


# Authentication
# Decorator order: route -> limiter -> jwt_required, so requests with a
# missing/invalid token are rate-limited too.

@app.post("/api/auth/register")
@limiter.limit("5 per hour")
def register():
    data = json_body()

    email = clean_string(data.get("email"), 256).lower()
    password = data.get("password")
    name = clean_string(data.get("name"), 120) or None

    if not email or not isinstance(password, str) or not password:
        return jsonify({"error": "Email and password are required."}), 400

    # 256 so over-long input is rejected instead of silently truncated.
    if len(email) > 255 or not EMAIL_RE.match(email):
        return jsonify({"error": "A valid email address is required."}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    if len(password) > 256:
        return jsonify({"error": "Password is too long."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists."}), 409

    user = User(email=email, name=name, password_hash=generate_password_hash(password))
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Two simultaneous registrations with the same email.
        db.session.rollback()
        return jsonify({"error": "An account with this email already exists."}), 409

    return jsonify({**issue_tokens(user.id), "user": user_json(user)}), 201


@app.post("/api/auth/login")
@limiter.limit("10 per minute")
@limiter.limit("5 per minute", key_func=login_email_key)
def login():
    data = json_body()

    email = clean_string(data.get("email"), 255).lower()
    password = data.get("password")
    if not isinstance(password, str) or len(password) > 256:
        password = ""

    user = User.query.filter_by(email=email).first()

    # Always run one hash check so unknown emails aren't distinguishable by timing.
    valid = check_password_hash(
        user.password_hash if user else DUMMY_PASSWORD_HASH,
        password,
    )
    if not user or not valid:
        return jsonify({"error": "Invalid email or password."}), 401

    return jsonify({**issue_tokens(user.id), "user": user_json(user)})


@app.post("/api/auth/refresh")
@limiter.limit("30 per hour")
@jwt_required(refresh=True)
def refresh():
    user = current_user()
    if not user:
        return jsonify({"error": "Invalid authentication token."}), 401

    return jsonify({"access_token": create_access_token(identity=str(user.id))})


@app.get("/api/me")
@jwt_required()
def me():
    user = current_user()
    if not user:
        return jsonify({"error": "Invalid authentication token."}), 401
    return jsonify(user_json(user))


# Dashboard authentication handoff

@app.post("/api/auth/dashboard-code")
@limiter.limit("10 per minute")
@jwt_required()
def create_dashboard_code():
    """One-time code for opening the dashboard. Never put a JWT in the URL."""
    user = current_user()
    if not user:
        return jsonify({"error": "Invalid authentication token."}), 401

    # Housekeeping: drop expired/used codes.
    DashboardCode.query.filter(
        DashboardCode.expires_at < now_utc() - timedelta(hours=1)
    ).delete(synchronize_session=False)

    raw = secrets.token_urlsafe(32)
    db.session.add(
        DashboardCode(
            code_hash=hash_code(raw),
            user_id=user.id,
            expires_at=now_utc() + timedelta(minutes=2),
        )
    )
    db.session.commit()

    return jsonify({"url": f"{dashboard_url}/extension-login.html?code={raw}"})


@app.post("/api/auth/exchange-dashboard-code")
@limiter.limit("20 per minute")
def exchange_dashboard_code():
    raw = clean_string(json_body().get("code"), 512)
    if not raw:
        return jsonify({"error": "Code is required."}), 400

    code_hash = hash_code(raw)
    now = now_utc()

    # Atomic "claim": the old check-then-update let two parallel requests both
    # pass the used_at check and both receive tokens. This also avoids comparing
    # naive (SQLite) and aware datetimes in Python.
    claimed = (
        DashboardCode.query
        .filter(
            DashboardCode.code_hash == code_hash,
            DashboardCode.used_at.is_(None),
            DashboardCode.expires_at > now,
        )
        .update({"used_at": now}, synchronize_session=False)
    )

    if claimed != 1:
        db.session.rollback()
        return jsonify({"error": "Dashboard code is invalid or expired."}), 401

    record = DashboardCode.query.filter_by(code_hash=code_hash).first()
    user_id = record.user_id
    db.session.commit()

    return jsonify(issue_tokens(user_id))


# Submission API

@app.post("/api/submissions")
@limiter.limit("120 per hour")
@jwt_required()
def create_submission():
    """Accepts only successful submissions; counters come from the extension."""
    user = current_user()
    if not user:
        return jsonify({"error": "Invalid authentication token."}), 401

    data = json_body()

    if clean_string(data.get("verdict"), 100) != "Accepted":
        return jsonify({"error": "Only Accepted submissions are stored remotely."}), 400

    title = clean_string(data.get("title"), 500) or "Untitled problem"
    slug = clean_string(data.get("problemSlug"), 201).lower()
    url = clean_string(data.get("problemUrl"), 2001)
    language = clean_string(data.get("lang", "unknown"), 80) or "unknown"

    code = data.get("code", "")
    if not isinstance(code, str):
        return jsonify({"error": "code must be a string."}), 400
    code = code.replace("\x00", "")

    if not slug or not url:
        return jsonify({"error": "problemSlug and problemUrl are required."}), 400

    if not SLUG_RE.match(slug):
        return jsonify({"error": "problemSlug is not a valid slug."}), 400

    if len(url) > 2000 or not validate_problem_url(url, slug):
        return jsonify({"error": "problemUrl must be a valid LeetCode problem URL."}), 400

    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        return jsonify({"error": "Submitted code is too large."}), 413

    try:
        right_attempts = parse_counter(data.get("rightAttempts", 1), "rightAttempts", 1)
        wrong_attempts = parse_counter(data.get("wrongAttempts", 0), "wrongAttempts", 0)
        total_attempts = parse_counter(
            data.get("totalAttempts", right_attempts + wrong_attempts),
            "totalAttempts",
            1,
        )
        submitted_at = parse_timestamp(data.get("timestamp"))
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    if total_attempts != right_attempts + wrong_attempts:
        return jsonify({"error": "totalAttempts must equal rightAttempts + wrongAttempts."}), 400

    problem = Problem.query.filter_by(slug=slug).first()

    if not problem:
        problem = Problem(title=title, slug=slug, url=url)
        db.session.add(problem)
        try:
            db.session.flush()
        except IntegrityError:
            # Another request created the same problem at the same moment.
            db.session.rollback()
            problem = Problem.query.filter_by(slug=slug).first()
            if not problem:
                return jsonify({"error": "Could not store problem."}), 500
    # Existing problems are shared by all users, so one user must NOT be able
    # to overwrite their title/url (previously a link-injection vector).

    submission = Submission(
        user_id=user.id,
        problem_id=problem.id,
        code=code,
        language=language,
        verdict="Accepted",
        right_attempts=right_attempts,
        wrong_attempts=wrong_attempts,
        total_attempts=total_attempts,
        submitted_at=submitted_at,
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


# Dashboard statistics

def latest_successes_for_user(user_id):
    """Latest submission per problem, done in SQL (no loading every row + code)."""
    ranked = (
        db.session.query(
            Submission.id.label("id"),
            func.row_number()
            .over(
                partition_by=Submission.problem_id,
                order_by=(Submission.submitted_at.desc(), Submission.id.desc()),
            )
            .label("rn"),
        )
        .filter(Submission.user_id == user_id)
        .subquery()
    )

    return (
        Submission.query
        .options(joinedload(Submission.problem), defer(Submission.code))
        .join(ranked, Submission.id == ranked.c.id)
        .filter(ranked.c.rn == 1)
        .order_by(Submission.submitted_at.desc())
        .all()
    )


@app.get("/api/dashboard/summary")
@jwt_required()
def dashboard_summary():
    latest = latest_successes_for_user(user_id_from_token())

    right = sum(s.right_attempts for s in latest)
    wrong = sum(s.wrong_attempts for s in latest)
    total = sum(s.total_attempts for s in latest)

    problems = [
        {
            "id": s.problem.id,
            "title": s.problem.title,
            "slug": s.problem.slug,
            "url": s.problem.url,
            "correct": s.right_attempts,
            "wrong": s.wrong_attempts,
            "attempts": s.total_attempts,
            "accuracy": accuracy_of(s.right_attempts, s.total_attempts),
            "last_solved_at": as_utc(s.submitted_at).isoformat(),
        }
        for s in latest
    ]

    return jsonify({
        "overall": {
            "solved_problems": len(latest),
            "correct": right,
            "wrong": wrong,
            "total": total,
            "accuracy": accuracy_of(right, total),
        },
        "problems": problems,
    })


# Problem detail

@app.get("/api/problems/<slug>")
@jwt_required()
def problem_detail(slug):
    slug = clean_string(slug, 500).lower()
    user_id = user_id_from_token()

    problem = Problem.query.filter_by(slug=slug).first()
    if not problem:
        return jsonify({"error": "Problem not found."}), 404

    submissions = (
        Submission.query
        .filter_by(user_id=user_id, problem_id=problem.id)
        .order_by(Submission.submitted_at.desc(), Submission.id.desc())
        .limit(100)
        .all()
    )

    if not submissions:
        return jsonify({"error": "No successful submission for this problem."}), 404

    latest = submissions[0]

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
            "accuracy": accuracy_of(latest.right_attempts, latest.total_attempts),
        },
        "submissions": [
            {
                "id": s.id,
                "verdict": s.verdict,
                "language": s.language,
                "submitted_at": as_utc(s.submitted_at).isoformat(),
                "code": s.code,
                "right_attempts": s.right_attempts,
                "wrong_attempts": s.wrong_attempts,
                "total_attempts": s.total_attempts,
            }
            for s in submissions
        ],
    })


# Run (development only; use Gunicorn in production)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)