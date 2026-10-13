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
import ast
import json
import threading
import urllib.request
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

# AI provider config (OpenRouter)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-3-27b-it:free")
AI_ENABLED = bool(OPENROUTER_API_KEY)


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


class Topic(db.Model):
    """DSA topic reference - seeded once, never changed by users."""
    __tablename__ = "topics"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=True)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)


class SkillScore(db.Model):
    """Per-user per-topic skill score, updated after each evaluation."""
    __tablename__ = "skill_scores"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False)
    score = db.Column(db.Float, nullable=False, default=0.0)  # 0-100
    confidence = db.Column(db.Float, nullable=False, default=0.0)  # 0-1
    problems_seen = db.Column(db.Integer, nullable=False, default=0)
    last_updated = db.Column(db.DateTime(timezone=True), nullable=False,
                             default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint("user_id", "topic_id", name="uq_skill_user_topic"),)

    topic = db.relationship("Topic", backref=db.backref("skill_scores", lazy=True))


class Evaluation(db.Model):
    """Rule-based evaluation result for one submission."""
    __tablename__ = "evaluations"
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id"),
                              unique=True, nullable=False, index=True)
    # Scores 0-100
    correctness_score = db.Column(db.Float, nullable=True)
    approach_score = db.Column(db.Float, nullable=True)
    complexity_score = db.Column(db.Float, nullable=True)
    optimization_score = db.Column(db.Float, nullable=True)
    coverage_score = db.Column(db.Float, nullable=True)
    overall_score = db.Column(db.Float, nullable=True)
    # Detected info
    time_complexity = db.Column(db.String(50), nullable=True)
    space_complexity = db.Column(db.String(50), nullable=True)
    detected_patterns = db.Column(db.Text, nullable=True)  # JSON list
    detected_topics = db.Column(db.Text, nullable=True)    # JSON list of topic slugs
    # Status: pending, done, failed
    status = db.Column(db.String(20), nullable=False, default="pending")
    error_message = db.Column(db.Text, nullable=True)
    evaluated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    submission = db.relationship("Submission", backref=db.backref("evaluation", uselist=False))


class AIReport(db.Model):
    """AI-generated learning report snapshot per user."""
    __tablename__ = "ai_reports"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    # JSON blob with structured report
    content = db.Column(db.Text, nullable=False)
    model_used = db.Column(db.String(120), nullable=True)
    # Status: pending, done, failed
    status = db.Column(db.String(20), nullable=False, default="pending")
    error_message = db.Column(db.Text, nullable=True)
    submissions_hash = db.Column(db.String(64), nullable=True)  # to detect meaningful changes
    generated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))


class UserGoal(db.Model):
    """User's learning goal - placement, exam, general DSA."""
    __tablename__ = "user_goals"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    goal_type = db.Column(db.String(60), nullable=False, default="general")  # placement, exam, general
    target_date = db.Column(db.Date, nullable=True)
    daily_target_minutes = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))


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
    return {"id": user.id, "email": user.email, "name": user.name or ""}


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


# ============================================================
# DSA Evaluation Engine
# ============================================================

# Score weights (configurable via env)
W_CORRECTNESS = float(os.getenv("W_CORRECTNESS", "0.25"))
W_APPROACH = float(os.getenv("W_APPROACH", "0.30"))
W_COMPLEXITY = float(os.getenv("W_COMPLEXITY", "0.20"))
W_OPTIMIZATION = float(os.getenv("W_OPTIMIZATION", "0.15"))
W_COVERAGE = float(os.getenv("W_COVERAGE", "0.10"))

# Pattern keywords for heuristic detection
PATTERN_KEYWORDS = {
    "two-pointers": ["left", "right", "low", "high", "pointer", "two_pointer"],
    "sliding-window": ["window", "sliding", "max_len", "min_len", "window_size"],
    "dynamic-programming": ["dp", "memo", "cache", "lru_cache", "functools", "tabulation"],
    "binary-search": ["binary_search", "bisect", "mid", "lo", "hi"],
    "bfs": ["bfs", "queue", "deque", "level_order"],
    "dfs": ["dfs", "stack", "recursive", "backtrack"],
    "hash-map": ["hashmap", "dict", "counter", "defaultdict", "set"],
    "heap": ["heap", "heapq", "priority_queue", "heappush", "heappop"],
    "greedy": ["greedy", "sort", "sorted"],
    "divide-conquer": ["merge_sort", "quick_sort", "divide"],
    "graph": ["graph", "adjacency", "neighbor", "visited", "union_find"],
    "tree": ["tree", "node", "root", "leaf", "inorder", "preorder", "postorder", "trie"],
    "stack": ["stack", "monotonic"],
    "backtracking": ["backtrack", "permut", "combin", "subset"],
    "sorting": ["sort", "merge", "quick", "counting_sort", "radix"],
    "bit-manipulation": ["xor", "&", "|", "<<", ">>", "bit"],
    "math": ["gcd", "lcm", "prime", "factorial", "sqrt", "math"],
    "string": ["str", "string", "substr", "palindrome", "anagram"],
    "linked-list": ["linked", "node", "next", "head", "tail", "ListNode"],
    "interval": ["interval", "overlap", "merge", "start", "end"],
}

TOPIC_SLUG_MAP = {
    "two-pointers": "two-pointers",
    "sliding-window": "sliding-window",
    "dynamic-programming": "dynamic-programming",
    "binary-search": "binary-search",
    "bfs": "graphs",
    "dfs": "graphs",
    "hash-map": "hash-maps",
    "heap": "heaps",
    "greedy": "greedy",
    "divide-conquer": "divide-and-conquer",
    "graph": "graphs",
    "tree": "trees",
    "stack": "stacks-queues",
    "backtracking": "backtracking",
    "sorting": "sorting",
    "bit-manipulation": "bit-manipulation",
    "math": "math",
    "string": "strings",
    "linked-list": "linked-lists",
    "interval": "intervals",
}


def detect_patterns(code: str) -> list[str]:
    """Heuristically detect DSA patterns from code text."""
    if not code:
        return []
    code_lower = code.lower()
    found = []
    for pattern, keywords in PATTERN_KEYWORDS.items():
        if any(kw in code_lower for kw in keywords):
            found.append(pattern)
    return found


def estimate_complexity(code: str, lang: str) -> tuple[str, str]:
    """Estimate time/space complexity using heuristic rules."""
    if not code:
        return "unknown", "unknown"
    code_lower = code.lower()
    lines = code.split("\n")
    # Count nested loops as proxy for time complexity
    loop_keywords = ["for ", "while "]
    loop_count = sum(
        1 for line in lines
        if any(kw in line.lower() for kw in loop_keywords)
    )
    has_recursion = "def " in code and any(fn in code for fn in ["self(", "dfs(", "helper(", "solve(", "backtrack("])
    has_nested = any(
        lines[i].count("for ") + lines[i].count("while ") > 0 and
        lines[j].count("for ") + lines[j].count("while ") > 0
        for i in range(len(lines))
        for j in range(i + 1, min(i + 6, len(lines)))
    ) if len(lines) > 1 else False

    # Time complexity
    if has_nested or loop_count >= 2:
        time_c = "O(n²)" if not has_recursion else "O(2ⁿ)"
    elif loop_count == 1:
        time_c = "O(n)"
    elif has_recursion:
        time_c = "O(n)"
    else:
        time_c = "O(1)"

    # Space complexity
    has_extra_space = any(kw in code_lower for kw in ["dict(", "set(", "list(", "defaultdict", "{}" , "[]"])
    space_c = "O(n)" if (has_extra_space or has_recursion) else "O(1)"

    return time_c, space_c


def score_correctness(submission) -> float:
    """Correctness score based on verdict and attempts."""
    if submission.verdict != "Accepted":
        return 0.0
    # Accepted on first try = 100, more wrong attempts = lower score
    wrong = submission.wrong_attempts
    score = max(40.0, 100.0 - (wrong * 15.0))
    return min(100.0, score)


def score_approach(patterns: list[str]) -> float:
    """Approach quality score based on detected patterns."""
    if not patterns:
        return 50.0  # neutral when we can't detect
    # Premium patterns (preferred approaches)
    premium = {"two-pointers", "sliding-window", "binary-search", "dynamic-programming",
               "heap", "greedy", "bit-manipulation"}
    base_patterns = {"hash-map", "sorting", "bfs", "dfs", "graph"}
    score = 50.0
    for p in patterns:
        if p in premium:
            score += 15.0
        elif p in base_patterns:
            score += 8.0
        else:
            score += 3.0
    return min(100.0, score)


def score_complexity(time_c: str, space_c: str) -> float:
    """Complexity efficiency score."""
    time_scores = {"O(1)": 100, "O(log n)": 95, "O(n)": 80, "O(n log n)": 65,
                   "O(n²)": 40, "O(2ⁿ)": 20, "O(n!)": 10, "unknown": 60}
    space_scores = {"O(1)": 100, "O(log n)": 90, "O(n)": 70, "O(n²)": 40, "unknown": 65}
    t = time_scores.get(time_c, 60)
    s = space_scores.get(space_c, 65)
    return round((t * 0.6 + s * 0.4), 1)


def score_optimization(code: str, patterns: list[str], time_c: str) -> float:
    """Optimization score - looks for efficient constructs."""
    if not code:
        return 50.0
    code_lower = code.lower()
    score = 50.0
    # Bonus for using built-ins and efficient data structures
    if "collections" in code_lower:
        score += 10
    if "bisect" in code_lower:
        score += 10
    if "heapq" in code_lower:
        score += 10
    if time_c in ["O(1)", "O(log n)", "O(n)"]:
        score += 15
    # Penalty for obviously bad patterns
    if ".sort()" in code and len(patterns) == 0:
        score -= 5
    return min(100.0, max(0.0, score))


def score_coverage(user_id: int, topic_slugs: list[str]) -> float:
    """Coverage score based on how many of the user's solved problems touch these topics."""
    if not topic_slugs:
        return 50.0
    # Count how many problems the user has solved
    total = Submission.query.filter_by(user_id=user_id, verdict="Accepted").count()
    if total == 0:
        return 30.0
    # Simple: more problems = better coverage
    score = min(100.0, 30.0 + (total * 5.0))
    return score


def compute_overall_score(c, a, cx, o, cv) -> float:
    """Weighted overall DSA skill score."""
    # Only include non-None dimensions
    parts = [(c, W_CORRECTNESS), (a, W_APPROACH), (cx, W_COMPLEXITY),
             (o, W_OPTIMIZATION), (cv, W_COVERAGE)]
    valid = [(s, w) for s, w in parts if s is not None]
    if not valid:
        return 0.0
    total_w = sum(w for _, w in valid)
    weighted = sum(s * w for s, w in valid)
    return round(weighted / total_w, 1)


def evaluate_submission(submission_id: int):
    """Run evaluation for a submission synchronously (called from thread)."""
    with app.app_context():
        try:
            sub = db.session.get(Submission, submission_id)
            if not sub:
                return
            ev = Evaluation.query.filter_by(submission_id=submission_id).first()
            if not ev:
                ev = Evaluation(submission_id=submission_id, status="pending")
                db.session.add(ev)
                db.session.flush()

            patterns = detect_patterns(sub.code)
            time_c, space_c = estimate_complexity(sub.code, sub.language)
            topic_slugs = list({TOPIC_SLUG_MAP.get(p) for p in patterns if TOPIC_SLUG_MAP.get(p)})

            c_score = score_correctness(sub)
            a_score = score_approach(patterns)
            cx_score = score_complexity(time_c, space_c)
            o_score = score_optimization(sub.code, patterns, time_c)
            cv_score = score_coverage(sub.user_id, topic_slugs)
            overall = compute_overall_score(c_score, a_score, cx_score, o_score, cv_score)

            ev.correctness_score = c_score
            ev.approach_score = a_score
            ev.complexity_score = cx_score
            ev.optimization_score = o_score
            ev.coverage_score = cv_score
            ev.overall_score = overall
            ev.time_complexity = time_c
            ev.space_complexity = space_c
            ev.detected_patterns = json.dumps(patterns)
            ev.detected_topics = json.dumps(topic_slugs)
            ev.status = "done"
            ev.evaluated_at = datetime.now(timezone.utc)

            # Update per-topic skill scores
            for slug in topic_slugs:
                topic = Topic.query.filter_by(slug=slug).first()
                if not topic:
                    name = slug.replace("-", " ").title()
                    topic = Topic(name=name, slug=slug)
                    db.session.add(topic)
                    db.session.flush()
                skill = SkillScore.query.filter_by(
                    user_id=sub.user_id, topic_id=topic.id
                ).first()
                if not skill:
                    skill = SkillScore(user_id=sub.user_id, topic_id=topic.id,
                                       score=0.0, confidence=0.0, problems_seen=0)
                    db.session.add(skill)
                    db.session.flush()
                # Exponential moving average of score
                alpha = 0.4
                skill.score = round(alpha * overall + (1 - alpha) * skill.score, 1)
                skill.problems_seen += 1
                skill.confidence = min(1.0, skill.problems_seen / 5.0)
                skill.last_updated = datetime.now(timezone.utc)

            db.session.commit()
            logger.info("Evaluation done for submission %d: overall=%.1f", submission_id, overall)
        except Exception as exc:
            logger.exception("Evaluation failed for submission %d", submission_id)
            try:
                ev = Evaluation.query.filter_by(submission_id=submission_id).first()
                if ev:
                    ev.status = "failed"
                    ev.error_message = str(exc)
                    db.session.commit()
            except Exception:
                db.session.rollback()


def trigger_evaluation(submission_id: int):
    """Fire-and-forget: run evaluation in a background thread."""
    t = threading.Thread(target=evaluate_submission, args=(submission_id,), daemon=True)
    t.start()


# ============================================================
# AI Report Generation (OpenRouter)
# ============================================================

def _build_report_prompt(user, submissions, evaluations) -> str:
    """Build the prompt for AI report generation."""
    sub_summaries = []
    for sub in submissions[:20]:  # cap at 20 to keep prompt size manageable
        ev = next((e for e in evaluations if e.submission_id == sub.id), None)
        patterns = json.loads(ev.detected_patterns or "[]") if ev else []
        sub_summaries.append(
            f"- {sub.problem.title} ({sub.language}): "
            f"verdict={sub.verdict}, wrong_attempts={sub.wrong_attempts}, "
            f"patterns={patterns}, "
            f"overall_score={ev.overall_score if ev else 'N/A'}"
        )
    subs_text = "\n".join(sub_summaries) if sub_summaries else "No submissions yet."

    return f"""You are a DSA learning coach analyzing a student's LeetCode practice data.

Student: {user.name or user.email}
Total solved problems: {len(submissions)}

Recent submission data:
{subs_text}

Provide a structured JSON learning report with these exact keys:
{{
  "strengths": ["list of 2-3 genuine strengths based on data"],
  "weaknesses": ["list of 2-3 areas needing improvement"],
  "skill_summary": "2-3 sentence overall assessment",
  "top_patterns": ["patterns they use most"],
  "recommendations": [
    {{"topic": "topic name", "reason": "why", "priority": "high/medium/low"}}
  ],
  "learning_path": ["ordered list of topics to study next"],
  "weekly_target": "specific achievable weekly goal",
  "encouragement": "brief personalized motivational message"
}}

IMPORTANT:
- Base ALL insights on the actual submission data above.
- Do NOT invent scores or override the evaluation scores.
- Return ONLY valid JSON, no markdown, no explanation outside the JSON."""


def generate_ai_report(user_id: int, force: bool = False):
    """Generate AI report for a user. Called from background thread."""
    with app.app_context():
        try:
            user = db.session.get(User, user_id)
            if not user:
                return

            submissions = (
                Submission.query
                .options(joinedload(Submission.problem))
                .filter_by(user_id=user_id, verdict="Accepted")
                .order_by(Submission.submitted_at.desc())
                .limit(50)
                .all()
            )

            if not submissions:
                return

            # Hash to detect meaningful changes
            sub_ids = ",".join(str(s.id) for s in submissions)
            sub_hash = hashlib.sha256(sub_ids.encode()).hexdigest()[:16]

            # Check if we need to regenerate
            latest_report = (
                AIReport.query.filter_by(user_id=user_id, status="done")
                .order_by(AIReport.generated_at.desc())
                .first()
            )
            if not force and latest_report and latest_report.submissions_hash == sub_hash:
                return  # No meaningful change

            if not AI_ENABLED:
                # Rule-based fallback when no AI key is configured
                report_content = _rule_based_report(user, submissions)
                record = AIReport(
                    user_id=user_id,
                    content=json.dumps(report_content),
                    model_used="rule-based",
                    status="done",
                    submissions_hash=sub_hash,
                    generated_at=datetime.now(timezone.utc),
                )
                db.session.add(record)
                db.session.commit()
                return

            # Get evaluations for context
            sub_ids_list = [s.id for s in submissions]
            evaluations = Evaluation.query.filter(
                Evaluation.submission_id.in_(sub_ids_list),
                Evaluation.status == "done"
            ).all()

            prompt = _build_report_prompt(user, submissions, evaluations)

            # Create pending record
            record = AIReport(
                user_id=user_id,
                content="{}",
                model_used=OPENROUTER_MODEL,
                status="pending",
                submissions_hash=sub_hash,
            )
            db.session.add(record)
            db.session.commit()

            # Call OpenRouter API
            payload = json.dumps({
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1200,
                "temperature": 0.3,
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=payload,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://learnsense-ai.com",
                    "X-Title": "LearnSense AI",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_body = json.loads(resp.read().decode("utf-8"))

            ai_text = resp_body["choices"][0]["message"]["content"].strip()
            # Parse JSON from AI response
            report_data = json.loads(ai_text)

            record.content = json.dumps(report_data)
            record.status = "done"
            record.generated_at = datetime.now(timezone.utc)
            db.session.commit()
            logger.info("AI report generated for user %d", user_id)

        except Exception as exc:
            logger.exception("AI report generation failed for user %d", user_id)
            try:
                record = (
                    AIReport.query.filter_by(user_id=user_id, status="pending")
                    .order_by(AIReport.created_at.desc())
                    .first()
                )
                if record:
                    record.status = "failed"
                    record.error_message = str(exc)[:500]
                    db.session.commit()
            except Exception:
                db.session.rollback()


def _rule_based_report(user, submissions) -> dict:
    """Fallback report when AI is not available."""
    total = len(submissions)
    langs = {}
    for s in submissions:
        langs[s.language] = langs.get(s.language, 0) + 1
    top_lang = max(langs, key=langs.get) if langs else "unknown"

    wrong_counts = [s.wrong_attempts for s in submissions]
    avg_wrong = sum(wrong_counts) / len(wrong_counts) if wrong_counts else 0

    # Aggregate patterns
    all_patterns = []
    for s in submissions:
        if s.evaluation and s.evaluation.detected_patterns:
            all_patterns.extend(json.loads(s.evaluation.detected_patterns))
    pattern_freq = {}
    for p in all_patterns:
        pattern_freq[p] = pattern_freq.get(p, 0) + 1
    top_patterns = sorted(pattern_freq, key=pattern_freq.get, reverse=True)[:3]

    strengths = []
    weaknesses = []
    if total >= 10:
        strengths.append("Consistent practice with " + str(total) + " problems solved")
    if avg_wrong < 1:
        strengths.append("High first-attempt success rate")
    elif avg_wrong > 3:
        weaknesses.append("Multiple wrong attempts per problem on average")
    if top_lang:
        strengths.append(f"Comfortable with {top_lang}")
    if not top_patterns:
        weaknesses.append("Limited pattern diversity detected")

    recommendations = [
        {"topic": "Dynamic Programming", "reason": "Widely tested in interviews", "priority": "high"},
        {"topic": "Graph Algorithms", "reason": "BFS/DFS essential for many problems", "priority": "high"},
        {"topic": "Binary Search", "reason": "Efficient search pattern used frequently", "priority": "medium"},
    ]

    return {
        "strengths": strengths or ["Keep practicing!"],
        "weaknesses": weaknesses or ["Continue building problem diversity"],
        "skill_summary": f"You have solved {total} problems in {top_lang}. Keep building your pattern library.",
        "top_patterns": top_patterns or ["Not enough data yet"],
        "recommendations": recommendations,
        "learning_path": ["Arrays & Hashing", "Two Pointers", "Sliding Window",
                          "Binary Search", "Linked Lists", "Trees", "Graphs", "DP"],
        "weekly_target": "Solve 5 problems covering 3 different topics",
        "encouragement": f"Great job solving {total} problems! Keep the momentum going.",
    }


def trigger_ai_report(user_id: int, force: bool = False):
    """Fire-and-forget: generate AI report in background thread."""
    t = threading.Thread(target=generate_ai_report, args=(user_id, force), daemon=True)
    t.start()


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

    email = clean_string(data.get("email"), 255).lower()
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
        DashboardCode.expires_at < now_utc()
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

    
    return jsonify({
    "url": f"{dashboard_url}/extension-login.html?code={raw}"
        })



@app.post("/api/auth/exchange-dashboard-code")
@limiter.limit("20 per minute")
def exchange_dashboard_code():
    raw = clean_string(json_body().get("code"), 512)
    if not raw:
        return jsonify({"error": "Code is required."}), 400

    code_hash = hash_code(raw)
    now = now_utc()

    # Atomic "claim": lock the row first, then mark as used.
    # Using with_for_update() prevents two parallel requests from both
    # claiming the same code, while keeping the record available in session.
    record = (
        DashboardCode.query
        .filter(
            DashboardCode.code_hash == code_hash,
            DashboardCode.used_at.is_(None),
            DashboardCode.expires_at > now,
        )
        .with_for_update()
        .first()
    )

    if not record:
        return jsonify({"error": "Dashboard code is invalid or expired."}), 401

    record.used_at = now
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
    slug = clean_string(data.get("problemSlug"), 200).lower()
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

    # Fire background evaluation
    trigger_evaluation(submission.id)
    # Check if AI report needs regeneration (throttled)
    trigger_ai_report(user.id)

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


# ============================================================
# Evaluation endpoints
# ============================================================

@app.get("/api/evaluations/<int:submission_id>")
@jwt_required()
def get_evaluation(submission_id):
    uid = user_id_from_token()
    sub = Submission.query.filter_by(id=submission_id, user_id=uid).first()
    if not sub:
        return jsonify({"error": "Submission not found."}), 404
    ev = Evaluation.query.filter_by(submission_id=submission_id).first()
    if not ev:
        return jsonify({"status": "not_evaluated"}), 200
    return jsonify({
        "status": ev.status,
        "overall_score": ev.overall_score,
        "correctness_score": ev.correctness_score,
        "approach_score": ev.approach_score,
        "complexity_score": ev.complexity_score,
        "optimization_score": ev.optimization_score,
        "coverage_score": ev.coverage_score,
        "time_complexity": ev.time_complexity,
        "space_complexity": ev.space_complexity,
        "detected_patterns": json.loads(ev.detected_patterns or "[]"),
        "detected_topics": json.loads(ev.detected_topics or "[]"),
        "evaluated_at": as_utc(ev.evaluated_at).isoformat() if ev.evaluated_at else None,
    })


# ============================================================
# Skill score endpoints
# ============================================================

@app.get("/api/skills")
@jwt_required()
def get_skill_scores():
    uid = user_id_from_token()
    scores = (
        SkillScore.query
        .filter_by(user_id=uid)
        .options(joinedload(SkillScore.topic))
        .order_by(SkillScore.score.desc())
        .all()
    ) if hasattr(SkillScore, 'query') else []

    # Add relationship if missing
    skill_list = []
    for s in scores:
        topic_name = s.topic.name if hasattr(s, 'topic') and s.topic else "Unknown"
        topic_slug = s.topic.slug if hasattr(s, 'topic') and s.topic else ""
        skill_list.append({
            "topic": topic_name,
            "topic_slug": topic_slug,
            "score": s.score,
            "confidence": s.confidence,
            "problems_seen": s.problems_seen,
            "last_updated": as_utc(s.last_updated).isoformat() if s.last_updated else None,
        })

    # Overall DSA score = weighted average of all topic scores
    if skill_list:
        total_weight = sum(s["problems_seen"] for s in skill_list)
        if total_weight > 0:
            overall = sum(s["score"] * s["problems_seen"] for s in skill_list) / total_weight
        else:
            overall = 0.0
    else:
        overall = 0.0

    return jsonify({
        "overall_score": round(overall, 1),
        "topics": skill_list,
    })


# ============================================================
# AI Report endpoints
# ============================================================

@app.get("/api/report")
@jwt_required()
def get_report():
    uid = user_id_from_token()
    report = (
        AIReport.query.filter_by(user_id=uid, status="done")
        .order_by(AIReport.generated_at.desc())
        .first()
    )
    if not report:
        # Check if one is pending
        pending = AIReport.query.filter_by(user_id=uid, status="pending").first()
        if pending:
            return jsonify({"status": "pending"}), 202
        # Trigger generation and return
        trigger_ai_report(uid)
        return jsonify({"status": "generating"}), 202

    return jsonify({
        "status": "done",
        "model": report.model_used,
        "generated_at": as_utc(report.generated_at).isoformat() if report.generated_at else None,
        "report": json.loads(report.content),
    })


@app.post("/api/report/regenerate")
@limiter.limit("5 per hour")
@jwt_required()
def regenerate_report():
    uid = user_id_from_token()
    trigger_ai_report(uid, force=True)
    return jsonify({"status": "generating"}), 202


# ============================================================
# User goals
# ============================================================

@app.get("/api/goals")
@jwt_required()
def get_goal():
    uid = user_id_from_token()
    goal = UserGoal.query.filter_by(user_id=uid).first()
    if not goal:
        return jsonify({"goal": None})
    return jsonify({
        "goal": {
            "type": goal.goal_type,
            "target_date": goal.target_date.isoformat() if goal.target_date else None,
            "daily_target_minutes": goal.daily_target_minutes,
            "notes": goal.notes,
        }
    })


@app.put("/api/goals")
@jwt_required()
def set_goal():
    uid = user_id_from_token()
    data = json_body()
    goal_type = clean_string(data.get("type", "general"), 60)
    if goal_type not in {"placement", "exam", "general"}:
        goal_type = "general"
    notes = clean_string(data.get("notes", ""), 500) or None
    daily = data.get("daily_target_minutes")
    if isinstance(daily, (int, float)) and not isinstance(daily, bool):
        daily = max(0, min(480, int(daily)))
    else:
        daily = None

    goal = UserGoal.query.filter_by(user_id=uid).first()
    if not goal:
        goal = UserGoal(user_id=uid)
        db.session.add(goal)
    goal.goal_type = goal_type
    goal.notes = notes
    goal.daily_target_minutes = daily
    db.session.commit()
    return jsonify({"ok": True})


# ============================================================
# Enhanced dashboard summary with skill scores
# ============================================================

@app.get("/api/dashboard/full")
@jwt_required()
def dashboard_full():
    """Full dashboard data: summary + skill scores + latest report status."""
    uid = user_id_from_token()
    user = db.session.get(User, uid)
    if not user:
        return jsonify({"error": "User not found."}), 404

    latest = latest_successes_for_user(uid)
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

    # Skill scores
    skill_scores = (
        SkillScore.query
        .filter_by(user_id=uid)
        .options(joinedload(SkillScore.topic))
        .order_by(SkillScore.score.desc())
        .all()
    )
    topics = []
    overall_skill = 0.0
    if skill_scores:
        total_weight = sum(s.problems_seen for s in skill_scores)
        if total_weight > 0:
            overall_skill = sum(s.score * s.problems_seen for s in skill_scores) / total_weight
        for s in skill_scores:
            topics.append({
                "topic": s.topic.name if s.topic else "Unknown",
                "topic_slug": s.topic.slug if s.topic else "",
                "score": s.score,
                "confidence": s.confidence,
                "problems_seen": s.problems_seen,
                "label": _skill_label(s.score, s.confidence),
            })

    # Latest AI report status
    report = (
        AIReport.query.filter_by(user_id=uid)
        .order_by(AIReport.created_at.desc())
        .first()
    )
    report_status = report.status if report else "none"

    # Streak: consecutive days with a submission
    streak = _calculate_streak(uid)

    return jsonify({
        "user": {"id": user.id, "email": user.email, "name": user.name or ""},
        "overall": {
            "solved_problems": len(latest),
            "correct": right,
            "wrong": wrong,
            "total": total,
            "accuracy": accuracy_of(right, total),
            "overall_skill_score": round(overall_skill, 1),
            "streak_days": streak,
        },
        "problems": problems,
        "topics": topics,
        "report_status": report_status,
    })


def _skill_label(score: float, confidence: float) -> str:
    if confidence < 0.3:
        return "Provisional"
    if score >= 85:
        return "Expert"
    if score >= 70:
        return "Proficient"
    if score >= 55:
        return "Developing"
    if score >= 35:
        return "Beginner"
    return "Novice"


def _calculate_streak(user_id: int) -> int:
    """Count consecutive days with at least one submission."""
    try:
        subs = (
            Submission.query
            .filter_by(user_id=user_id)
            .order_by(Submission.submitted_at.desc())
            .limit(366)
            .all()
        )
        if not subs:
            return 0
        days = sorted(
            {as_utc(s.submitted_at).date() for s in subs},
            reverse=True,
        )
        streak = 1
        today = datetime.now(timezone.utc).date()
        if days[0] < today - timedelta(days=1):
            return 0
        for i in range(len(days) - 1):
            if (days[i] - days[i + 1]).days == 1:
                streak += 1
            else:
                break
        return streak
    except Exception:
        return 0


# Run (development only; use Gunicorn in production)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)