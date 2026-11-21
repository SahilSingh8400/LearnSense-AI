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
import socket
import threading
import urllib.request

socket.setdefaulttimeout(10)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash


# Environment / logging

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
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
APP_ENV = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development"))
IS_PROD = APP_ENV == "production"

# AI provider config (OpenRouter and Gemini direct)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "liquid/lfm-3-1.7b:free")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
AI_ENABLED = bool(OPENROUTER_API_KEY or GEMINI_API_KEY)


# Flask app

app = Flask(__name__)

if os.getenv("TRUST_PROXY", "0") == "1":
    # Needed behind Nginx/Render/Heroku etc., otherwise every client shares
    # the proxy's IP and the rate limiter blocks everybody together.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.config["MAX_CONTENT_LENGTH"] = int(
    os.getenv("MAX_CONTENT_LENGTH", str(2 * 1024 * 1024))
)

instance_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "instance"))
os.makedirs(instance_dir, exist_ok=True)
db_file = os.path.join(instance_dir, "learnsense.db").replace("\\", "/")
database_url = os.getenv("DATABASE_URL", f"sqlite:///{db_file}")
if database_url in {"sqlite:///learnsense.db", "sqlite:///./learnsense.db"}:
    database_url = f"sqlite:///{db_file}"
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
            "origins": [dashboard_origin, "http://localhost:5000", "http://127.0.0.1:5000", "http://localhost:3000", "null"],
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
        }
    },
)


@app.before_request
def handle_cors_preflight():
    if request.method == "OPTIONS" and request.path.startswith("/api/"):
        origin = request.headers.get("Origin", "*")
        resp = app.make_default_options_response()
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp


@app.after_request
def handle_cors_for_extensions(response):
    origin = request.headers.get("Origin", "")
    match = EXTENSION_ORIGIN_RE.match(origin)
    if request.path.startswith("/api/"):
        if match or origin in {dashboard_origin, "http://localhost:5000", "http://127.0.0.1:5000", "http://localhost:3000"}:
            response.headers["Access-Control-Allow-Origin"] = origin or "*"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )
            response.headers.add("Vary", "Origin")
    return response


# ============================================================
# Dashboard static files (Offline First: / and /dashboard)
# ============================================================

DASHBOARD_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "dashboard")
)


@app.get("/")
@app.get("/dashboard")
@app.get("/dashboard/")
def dashboard_home():
    return send_from_directory(DASHBOARD_DIR, "index.html")


@app.get("/dashboard/<path:filename>")
def dashboard_files(filename):
    return send_from_directory(DASHBOARD_DIR, filename)


@app.get("/<path:filename>")
def root_static_files(filename):
    # Route only non-api static files
    if not filename.startswith("api/"):
        target = os.path.join(DASHBOARD_DIR, filename)
        if os.path.isfile(target):
            return send_from_directory(DASHBOARD_DIR, filename)
    return send_from_directory(DASHBOARD_DIR, "index.html")


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
    expected_time_complexity = db.Column(db.String(50), nullable=True)
    expected_space_complexity = db.Column(db.String(50), nullable=True)
    is_optimal = db.Column(db.Boolean, nullable=True)
    ai_thought = db.Column(db.Text, nullable=True)
    expected_solution = db.Column(db.Text, nullable=True)
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
    "hash-map": ["hashmap", "dict", "counter", "defaultdict", "set", "unordered_map", "unordered_set", "map<"],
    "heap": ["heap", "heapq", "priority_queue", "heappush", "heappop"],
    "greedy": ["greedy", "sort", "sorted"],
    "divide-conquer": ["merge_sort", "quick_sort", "divide"],
    "graph": ["graph", "adjacency", "neighbor", "visited", "union_find"],
    "tree": ["tree", "node", "root", "leaf", "inorder", "preorder", "postorder", "trie"],
    "stack": ["stack", "monotonic"],
    "backtracking": ["backtrack", "permut", "combin", "subset"],
    "sorting": ["sort", "merge", "quick", "counting_sort", "radix"],
    "bit-manipulation": ["xor", "bitset", "bitcount", "hamming"],
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

# Canonical problem to DSA topic mapping for common LeetCode problems
PROBLEM_TOPIC_MAP = {
    "two-sum": ["hash-maps", "two-pointers"],
    "valid-anagram": ["hash-maps", "strings"],
    "group-anagrams": ["hash-maps", "sorting"],
    "contains-duplicate": ["hash-maps"],
    "top-k-frequent-elements": ["heaps", "hash-maps"],
    "product-of-array-except-self": ["arrays-and-hashing"],
    "longest-consecutive-sequence": ["hash-maps"],
    "valid-palindrome": ["two-pointers", "strings"],
    "3sum": ["two-pointers", "sorting"],
    "container-with-most-water": ["two-pointers"],
    "best-time-to-buy-and-sell-stock": ["two-pointers", "sliding-window"],
    "longest-substring-without-repeating-characters": ["sliding-window", "hash-maps"],
    "longest-repeating-character-replacement": ["sliding-window"],
    "minimum-window-substring": ["sliding-window", "hash-maps"],
    "valid-parentheses": ["stacks-queues"],
    "min-stack": ["stacks-queues"],
    "evaluate-reverse-polish-notation": ["stacks-queues"],
    "generate-parentheses": ["backtracking", "stacks-queues"],
    "daily-temperatures": ["stacks-queues"],
    "binary-search": ["binary-search"],
    "search-a-2d-matrix": ["binary-search"],
    "find-minimum-in-rotated-sorted-array": ["binary-search"],
    "search-in-rotated-sorted-array": ["binary-search"],
    "reverse-linked-list": ["linked-lists"],
    "merge-two-sorted-lists": ["linked-lists"],
    "reorder-list": ["linked-lists", "two-pointers"],
    "remove-nth-node-from-end-of-list": ["linked-lists", "two-pointers"],
    "linked-list-cycle": ["linked-lists", "two-pointers"],
    "invert-binary-tree": ["trees"],
    "maximum-depth-of-binary-tree": ["trees"],
    "diameter-of-binary-tree": ["trees"],
    "balanced-binary-tree": ["trees"],
    "same-tree": ["trees"],
    "subtree-of-another-tree": ["trees"],
    "lowest-common-ancestor-of-a-binary-search-tree": ["trees"],
    "binary-tree-level-order-traversal": ["trees", "graphs"],
    "validate-binary-search-tree": ["trees"],
    "kth-smallest-element-in-a-bst": ["trees"],
    "construct-binary-tree-from-preorder-and-inorder-traversal": ["trees"],
    "kth-largest-element-in-an-array": ["heaps"],
    "find-median-from-data-stream": ["heaps"],
    "combination-sum": ["backtracking"],
    "subsets": ["backtracking"],
    "subsets-ii": ["backtracking"],
    "permutations": ["backtracking"],
    "word-search": ["backtracking", "graphs"],
    "number-of-islands": ["graphs"],
    "clone-graph": ["graphs"],
    "pacific-atlantic-water-flow": ["graphs"],
    "course-schedule": ["graphs"],
    "climbing-stairs": ["dynamic-programming"],
    "min-cost-climbing-stairs": ["dynamic-programming"],
    "coin-change": ["dynamic-programming"],
    "longest-increasing-subsequence": ["dynamic-programming", "binary-search"],
    "maximum-subarray": ["dynamic-programming", "greedy"],
    "jump-game": ["greedy"],
    "gas-station": ["greedy"],
    "single-number": ["bit-manipulation"],
    "number-of-1-bits": ["bit-manipulation"],
    "counting-bits": ["bit-manipulation", "dynamic-programming"],
    "reverse-bits": ["bit-manipulation"],
    "missing-number": ["bit-manipulation", "arrays-and-hashing"],
}


def detect_patterns(code: str, lang: str = "") -> list[str]:
    """Heuristically detect DSA patterns from code text across languages."""
    if not code:
        return []
    code_lower = code.lower()
    found = set()

    if any(k in code_lower for k in ["hashmap", "unordered_map", "dict(", "counter(", "defaultdict", "set(", "unordered_set", "map<", "hashset", "treemap", "treeset", ".has(", "new map"]):
        found.add("hash-map")
    if any(k in code_lower for k in ["left", "right", "low", "high", "two_pointer", "i++", "j--", "left++", "right--"]):
        found.add("two-pointers")
    if any(k in code_lower for k in ["sliding", "window", "max_len", "min_len", "window_size", "right - left"]):
        found.add("sliding-window")
    if any(k in code_lower for k in ["binary_search", "bisect", "mid", "lower_bound", "upper_bound", "lo + (hi - lo)"]):
        found.add("binary-search")
    if any(k in code_lower for k in ["bfs", "queue", "deque", "level_order", "poll()", "popleft()"]):
        found.add("bfs")
    if any(k in code_lower for k in ["dfs", "backtrack", "helper(", "solve(", "preorder", "inorder", "postorder"]) and ("tree" in code_lower or "visited" in code_lower or "root" in code_lower or "node" in code_lower):
        found.add("dfs")
    if any(k in code_lower for k in ["heap", "heapq", "priority_queue", "priorityqueue", "heappush", "heappop"]):
        found.add("heap")
    if any(k in code_lower for k in ["dp[", "memo", "lru_cache", "tabulation", "bottom_up", "vector<vector<int>>"]):
        found.add("dynamic-programming")
    if any(k in code_lower for k in ["stack<", "stack[", "monotonic", "stack.append", "stack.pop", "push(", "pop()"]) and "unordered_map" not in code_lower:
        found.add("stack")
    if any(k in code_lower for k in ["treenode", "root", "leaf", "inorder", "preorder", "postorder", "bst"]):
        found.add("tree")
    if any(k in code_lower for k in ["listnode", "linked", "head", "tail", "next"]):
        found.add("linked-list")
    if any(k in code_lower for k in ["xor", "bitset", "bit_count", "bitcount", "hamming"]) or ("^" in code_lower and "^=" in code_lower):
        found.add("bit-manipulation")
    if any(k in code_lower for k in ["greedy", "max_profit", "intervals.sort"]):
        found.add("greedy")
    if any(k in code_lower for k in ["backtrack", "permut", "combin", "subsets", "candidates"]):
        found.add("backtracking")
    if any(k in code_lower for k in [".sort()", "sort(", "sorted(", "arrays.sort", "collections.sort"]):
        found.add("sorting")

    return sorted(list(found))


def detect_topics(problem_slug: str, code: str, lang: str = "") -> list[str]:
    """Combine canonical problem topic mapping and code pattern detection."""
    topics = set()
    if problem_slug and problem_slug in PROBLEM_TOPIC_MAP:
        topics.update(PROBLEM_TOPIC_MAP[problem_slug])
    patterns = detect_patterns(code, lang)
    for p in patterns:
        slug = TOPIC_SLUG_MAP.get(p)
        if slug:
            topics.add(slug)
    if not topics:
        topics.add("arrays-and-hashing")
    return sorted(list(topics))


def estimate_complexity(code: str, lang: str = "") -> tuple[str, str]:
    """Estimate time/space complexity using heuristic rules across languages."""
    if not code:
        return "unknown", "unknown"
    code_lower = code.lower()
    lines = [l.strip() for l in code.split("\n") if l.strip()]

    loop_count = 0
    for line in lines:
        if line.startswith("//") or line.startswith("#"):
            continue
        if any(line.startswith(kw) or f" {kw}" in line for kw in ["for ", "for(", "while ", "while("]):
            loop_count += 1

    has_recursion = any(fn in code_lower for fn in ["dfs(", "helper(", "solve(", "backtrack(", "traverse(", "quicksort(", "mergesort("])

    has_nested = False
    for i in range(len(lines)):
        l1 = lines[i].lower()
        if any(kw in l1 for kw in ["for ", "for(", "while ", "while("]):
            for j in range(i + 1, min(i + 8, len(lines))):
                l2 = lines[j].lower()
                if any(kw in l2 for kw in ["for ", "for(", "while ", "while("]):
                    has_nested = True
                    break
        if has_nested:
            break

    # Time complexity
    if any(kw in code_lower for kw in [
        "binary_search", "bisect", "mid = (lo + hi)", "mid = lo + (hi - lo)",
        "mid = (left + right)", "mid = left + (right - left)", "left <= right",
        "left < right", "lo <= hi", "lo < hi", "start <= end"
    ]) and not has_nested:
        time_c = "O(log n)"
    elif has_nested or (loop_count >= 2 and not any(k in code_lower for k in ["left++", "right--"])):
        time_c = "O(n²)" if not has_recursion else "O(2ⁿ)"
    elif any(kw in code_lower for kw in [".sort()", "sort(", "sorted(", "std::sort", "arrays.sort"]):
        time_c = "O(n log n)"
    elif loop_count >= 1 or has_recursion:
        time_c = "O(n)"
    else:
        time_c = "O(1)"

    # Space complexity
    has_extra_space = any(kw in code_lower for kw in [
        "dict(", "set(", "list(", "defaultdict", "{}", "[]",
        "unordered_map", "unordered_set", "vector<", "hashmap",
        "hashset", "arraylist", "new int[", "new map", "new set"
    ])
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

            analysis = analyze_solution_with_ai(sub, sub.problem)
            patterns = detect_patterns(sub.code, sub.language)
            time_c = analysis.get("time_complexity") or estimate_complexity(sub.code, sub.language)[0]
            space_c = analysis.get("space_complexity") or estimate_complexity(sub.code, sub.language)[1]
            topic_slugs = detect_topics(sub.problem.slug if sub.problem else "", sub.code, sub.language)

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
            ev.expected_time_complexity = analysis.get("expected_time_complexity")
            ev.expected_space_complexity = analysis.get("expected_space_complexity")
            ev.is_optimal = analysis.get("is_optimal", True)
            ev.ai_thought = analysis.get("ai_thought", "")
            ev.expected_solution = analysis.get("expected_solution", "")
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
# AI Performance Analysis & DSA Evaluation Engine
# ============================================================

def extract_json(text: str) -> dict:
    """Robustly parse JSON from AI model text output, stripping any markdown."""
    if not text:
        raise ValueError("Empty response from AI")
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]
    try:
        return json.loads(text)
    except Exception:
        return json.loads(text, strict=False)


def call_ai_api(prompt: str) -> tuple[dict, str]:
    """Call configured AI APIs with candidate fallbacks and return (parsed_data, model_name)."""
    # 1. Direct Gemini API if configured
    if GEMINI_API_KEY:
        gemini_candidates = [
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
        ]
        for g_model in gemini_candidates:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={GEMINI_API_KEY}"
                payload = json.dumps({
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 4096,
                        "responseMimeType": "application/json"
                    }
                }).encode("utf-8")
                req = urllib.request.Request(
                    url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
                )
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return extract_json(text), f"google/{g_model}"
            except Exception as e:
                logger.warning("Direct Gemini API attempt failed for %s: %s", g_model, e)
                continue

    # 2. OpenRouter API with multi-model fallback pool
    if OPENROUTER_API_KEY:
        candidate_models = [
            OPENROUTER_MODEL,
            "liquid/lfm-3-1.7b:free",
            "google/gemma-4-31b-it:free",
            "google/gemma-4-26b-a4b-it:free",
            "nvidia/nemotron-3.5-lightning:free",
            "openrouter/free",
        ]
        seen = set()
        models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

        for model in models_to_try:
            try:
                payload = json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2500,
                    "temperature": 0.2,
                }).encode("utf-8")
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    data=payload,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:5000",
                        "X-Title": "LearnSense AI",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp_body = json.loads(resp.read().decode("utf-8"))
                    choice = resp_body["choices"][0]["message"]
                    content = choice.get("content") or choice.get("reasoning")
                    if content:
                        try:
                            parsed = extract_json(content)
                            return parsed, model
                        except Exception as pe:
                            logger.warning("Could not extract JSON from %s output: %s", model, pe)
            except Exception as e:
                logger.warning("OpenRouter model %s failed: %s", model, e)
                continue

    raise RuntimeError("All AI API candidates were offline or rate-limited")


# ============================================================
# Problem Expected Complexity & AI Solution Analysis Engine
# ============================================================

PROBLEM_EXPECTED_COMPLEXITY = {
    "two-sum": ("O(n)", "O(n)"),
    "search-insert-position": ("O(log n)", "O(1)"),
    "binary-search": ("O(log n)", "O(1)"),
    "reverse-linked-list": ("O(n)", "O(1)"),
    "valid-anagram": ("O(n)", "O(1)"),
    "contains-duplicate": ("O(n)", "O(n)"),
    "valid-palindrome": ("O(n)", "O(1)"),
    "valid-parentheses": ("O(n)", "O(n)"),
    "merge-two-sorted-lists": ("O(n)", "O(1)"),
    "maximum-subarray": ("O(n)", "O(1)"),
    "climbing-stairs": ("O(n)", "O(1)"),
    "invert-binary-tree": ("O(n)", "O(h)"),
    "3sum": ("O(n²)", "O(1)"),
    "container-with-most-water": ("O(n)", "O(1)"),
    "best-time-to-buy-and-sell-stock": ("O(n)", "O(1)"),
    "longest-substring-without-repeating-characters": ("O(n)", "O(min(m, n))"),
}

CANONICAL_PROBLEM_DATA = {
    "search-insert-position": {
        "expected_time": "O(log n)",
        "expected_space": "O(1)",
        "thought": "The input array is already sorted, making Binary Search the optimal approach. In each iteration, comparing `target` with the midpoint halves the search interval. When the loop terminates (`left > right`), the `left` pointer index precisely points to the index where the target should be inserted to maintain sorted order.",
        "expected_solution": """class Solution {
public:
    int searchInsert(vector<int>& nums, int target) {
        int left = 0, right = nums.size() - 1;
        while (left <= right) {
            int mid = left + (right - left) / 2;
            if (nums[mid] == target) {
                return mid;
            } else if (nums[mid] < target) {
                left = mid + 1;
            } else {
                right = mid - 1;
            }
        }
        return left; // Insertion index
    }
};"""
    },
    "two-sum": {
        "expected_time": "O(n)",
        "expected_space": "O(n)",
        "thought": "A single-pass hash map (`unordered_map`) records each element and its index while traversing. For each index `i`, checking if `target - nums[i]` exists in the hash map takes O(1) average lookup time, achieving an optimal O(n) runtime and O(n) auxiliary space.",
        "expected_solution": """class Solution {
public:
    vector<int> twoSum(vector<int>& nums, int target) {
        unordered_map<int, int> seen;
        for (int i = 0; i < nums.size(); ++i) {
            int complement = target - nums[i];
            if (seen.count(complement)) {
                return {seen[complement], i};
            }
            seen[nums[i]] = i;
        }
        return {};
    }
};"""
    },
    "binary-search": {
        "expected_time": "O(log n)",
        "expected_space": "O(1)",
        "thought": "Classic iterative binary search maintains `left` and `right` pointers. Computing `mid = left + (right - left) / 2` protects against potential integer overflow. The search space decreases by half in every step, guaranteeing O(log n) time complexity and O(1) auxiliary space.",
        "expected_solution": """class Solution {
public:
    int search(vector<int>& nums, int target) {
        int left = 0, right = nums.size() - 1;
        while (left <= right) {
            int mid = left + (right - left) / 2;
            if (nums[mid] == target) return mid;
            if (nums[mid] < target) left = mid + 1;
            else right = mid - 1;
        }
        return -1;
    }
};"""
    },
    "reverse-linked-list": {
        "expected_time": "O(n)",
        "expected_space": "O(1)",
        "thought": "Iteratively reversing a singly linked list requires three pointers: `prev`, `curr`, and `nextTemp`. Traversing every node exactly once redirects its `next` pointer backwards in O(n) time and O(1) space, avoiding recursion call-stack overhead.",
        "expected_solution": """class Solution {
public:
    ListNode* reverseList(ListNode* head) {
        ListNode* prev = nullptr;
        ListNode* curr = head;
        while (curr != nullptr) {
            ListNode* nextTemp = curr->next;
            curr->next = prev;
            prev = curr;
            curr = nextTemp;
        }
        return prev;
    }
};"""
    }
}


def get_expected_complexity(slug: str, detected_patterns: list[str]) -> tuple[str, str]:
    if slug in PROBLEM_EXPECTED_COMPLEXITY:
        return PROBLEM_EXPECTED_COMPLEXITY[slug]
    if "binary-search" in detected_patterns:
        return "O(log n)", "O(1)"
    if "hash-map" in detected_patterns:
        return "O(n)", "O(n)"
    if "sorting" in detected_patterns:
        return "O(n log n)", "O(1)"
    return "O(n)", "O(1)"


def analyze_solution_with_ai(submission, problem=None) -> dict:
    """Analyze a single solution using AI (with canonical/rule fallback)."""
    if not problem and submission.problem:
        problem = submission.problem
    title = problem.title if problem else "DSA Problem"
    slug = problem.slug if problem else ""
    code = submission.code or ""
    lang = submission.language or "cpp"

    prompt = f"""You are an elite DSA Technical Interviewer and Algorithmic Complexity Evaluator.
Analyze the student's solution for the LeetCode problem "{title}" (slug: {slug}) written in {lang}.

Student's code:
```{lang}
{code}
```

Evaluate their solution and return ONLY valid JSON matching this schema:
{{
  "time_complexity": "O(log n)",
  "space_complexity": "O(1)",
  "expected_time_complexity": "O(log n)",
  "expected_space_complexity": "O(1)",
  "is_optimal": true,
  "ai_thought": "Comprehensive thought process and architectural feedback explaining why this code is optimal or how it can be improved.",
  "expected_solution": "// Clean, complete, optimal reference code in {lang} with explanatory comments"
}}

RULES:
1. "time_complexity" and "space_complexity" must accurately represent the student's submitted code using Big-O notation.
2. "expected_time_complexity" and "expected_space_complexity" must be the optimal theoretical bounds for this problem.
3. "is_optimal" must be true if the student's solution matches the optimal time & space complexity, or false if a faster approach exists.
4. "ai_thought" must be insightful, constructive, and explain algorithmic trade-offs.
5. "expected_solution" must be complete, idiomatic code in {lang}.
6. Return ONLY valid JSON, with NO markdown backticks outside the JSON."""

    ai_data = None
    if AI_ENABLED:
        try:
            ai_data, model_name = call_ai_api(prompt)
            logger.info("AI solution analysis successful for '%s' using %s", title, model_name)
        except Exception as e:
            logger.warning("AI solution analysis failed for '%s': %s", title, e)

    if (ai_data and isinstance(ai_data, dict) and 
        "time_complexity" in ai_data and "expected_solution" in ai_data):
        return ai_data

    # Fallback to high-accuracy canonical & rule engine
    time_c, space_c = estimate_complexity(code, lang)
    patterns = detect_patterns(code, lang)
    exp_time, exp_space = get_expected_complexity(slug, patterns)

    rank = {"O(1)": 1, "O(log n)": 2, "O(n)": 3, "O(n log n)": 4, "O(n²)": 5, "O(2ⁿ)": 6, "unknown": 4}
    is_opt = rank.get(time_c, 3) <= rank.get(exp_time, 3)

    canonical = CANONICAL_PROBLEM_DATA.get(slug)
    if canonical:
        exp_time = canonical["expected_time"]
        exp_space = canonical["expected_space"]
        thought = canonical["thought"]
        expected_code = canonical["expected_solution"]
        is_opt = (rank.get(time_c, 3) <= rank.get(exp_time, 3))
    else:
        pattern_str = ", ".join(p.replace("-", " ").title() for p in patterns) if patterns else "standard traversal"
        if is_opt:
            thought = (
                f"Your solution for '{title}' demonstrates an optimal algorithmic approach using {pattern_str}. "
                f"It achieves {time_c} time complexity and {space_c} auxiliary space, matching the theoretical best-case bound. "
                "The code structure is clean with proper pointer / variable handling."
            )
        else:
            thought = (
                f"Your solution for '{title}' runs in {time_c} time, but an optimal {exp_time} approach is possible. "
                f"Consider optimizing by leveraging {exp_time} techniques such as hash-based lookups or binary partitioning."
            )
        expected_code = code

    return {
        "time_complexity": time_c,
        "space_complexity": space_c,
        "expected_time_complexity": exp_time,
        "expected_space_complexity": exp_space,
        "is_optimal": is_opt,
        "ai_thought": thought,
        "expected_solution": expected_code,
    }


def _build_report_prompt(user, submissions, evaluations) -> str:
    """Build a detailed prompt for AI report generation."""
    sub_summaries = []
    for sub in submissions[:25]:
        ev = next((e for e in evaluations if e.submission_id == sub.id), None)
        patterns = json.loads(ev.detected_patterns or "[]") if ev else []
        topics = json.loads(ev.detected_topics or "[]") if ev else []
        sub_summaries.append(
            f"- Problem: '{sub.problem.title}' ({sub.language}) | "
            f"Verdict: {sub.verdict} | Wrong attempts: {sub.wrong_attempts} | "
            f"Complexity: {ev.time_complexity if ev else 'N/A'}, {ev.space_complexity if ev else 'N/A'} | "
            f"Topics: {topics} | Patterns: {patterns} | "
            f"Score: {ev.overall_score if ev else 'N/A'}"
        )
    subs_text = "\n".join(sub_summaries) if sub_summaries else "No submissions yet."

    return f"""You are an elite DSA Technical Interview Coach and Performance Analyst evaluating a student's practice data.

Student: {user.name or user.email}
Total solved problems: {len(submissions)}

Practice submission history:
{subs_text}

Analyze the student's performance and return ONLY valid JSON following this exact structure:
{{
  "strengths": ["Clean solution design", "Zero penalty attempts on first try"],
  "weaknesses": ["Broaden practice beyond initial topics"],
  "skill_summary": "Demonstrated sound algorithmic problem solving fundamentals and syntax mastery.",
  "top_patterns": ["Hash Maps", "Two Pointers"],
  "overall_dsa_score": 78,
  "skill_level": "Proficient",
  "topic_scores": [
    {{"topic": "Hash Maps", "slug": "hash-maps", "score": 82, "problems_seen": 1, "feedback": "Solid lookup optimization"}},
    {{"topic": "Two Pointers", "slug": "two-pointers", "score": 72, "problems_seen": 1, "feedback": "Good pointer control"}}
  ],
  "recommendations": [
    {{"topic": "Two Pointers", "reason": "Standard technique for array traversal and search", "priority": "high"}},
    {{"topic": "Binary Search", "reason": "Expands logarithmic search mastery", "priority": "medium"}}
  ],
  "learning_path": ["Arrays & Hashing", "Two Pointers", "Sliding Window", "Binary Search", "Trees", "Graphs", "DP"],
  "weekly_target": "Solve 5 problems covering 2 distinct topics",
  "encouragement": "Consistent daily problem solving builds lasting interview intuition."
}}

RULES:
1. "overall_dsa_score" MUST be an integer between 0 and 100 representing their overall DSA skill based on their solutions.
2. "skill_level" MUST be one of: "Novice" (0-34), "Beginner" (35-54), "Developing" (55-69), "Proficient" (70-84), "Expert" (85-100).
3. "topic_scores" must cover the student's practiced topics, with score 0-100.
4. Return ONLY valid JSON, with NO markdown code blocks and NO text before or after."""


def generate_ai_report(user_id: int, force: bool = False):
    """Generate AI learning report and synchronize DSA skill scores."""
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

            sub_ids = ",".join(str(s.id) for s in submissions)
            sub_hash = hashlib.sha256(sub_ids.encode()).hexdigest()[:16]

            latest_report = (
                AIReport.query.filter_by(user_id=user_id, status="done")
                .order_by(AIReport.generated_at.desc())
                .first()
            )
            if not force and latest_report and latest_report.submissions_hash == sub_hash:
                return

            # Ensure all submissions have done evaluations
            sub_ids_list = [s.id for s in submissions]
            evaluations = Evaluation.query.filter(
                Evaluation.submission_id.in_(sub_ids_list),
                Evaluation.status == "done"
            ).all()

            # Record or update pending report
            record = (
                AIReport.query.filter_by(user_id=user_id, status="pending")
                .order_by(AIReport.created_at.desc())
                .first()
            )
            if not record:
                record = AIReport(
                    user_id=user_id,
                    content="{}",
                    model_used=OPENROUTER_MODEL,
                    status="pending",
                    submissions_hash=sub_hash,
                )
                db.session.add(record)
                db.session.commit()

            report_data = None
            model_used = "dsa-performance-engine (offline)"

            # Call AI if enabled
            if AI_ENABLED:
                try:
                    prompt = _build_report_prompt(user, submissions, evaluations)
                    report_data, model_used = call_ai_api(prompt)
                    logger.info("AI report obtained from %s for user %d", model_used, user_id)
                except Exception as ai_err:
                    logger.warning("AI API call failed (%s), using high-precision performance engine", ai_err)

            # If AI was disabled or call failed, use robust algorithmic report
            if not report_data:
                report_data = _rule_based_report(user, submissions, evaluations)
                model_used = "dsa-performance-engine (local)"

            # Ensure overall_dsa_score & skill_level exist
            if "overall_dsa_score" not in report_data or not report_data["overall_dsa_score"]:
                t_scores = report_data.get("topic_scores", [])
                if t_scores:
                    report_data["overall_dsa_score"] = round(
                        sum(t.get("score", 70) * t.get("problems_seen", 1) for t in t_scores) /
                        max(1, sum(t.get("problems_seen", 1) for t in t_scores)), 1
                    )
                else:
                    report_data["overall_dsa_score"] = 75.0
            if "skill_level" not in report_data or not report_data["skill_level"]:
                report_data["skill_level"] = _skill_label(report_data["overall_dsa_score"], min(1.0, len(submissions) / 5.0))

            # Synchronize topic scores directly into skill_scores table
            for item in report_data.get("topic_scores", []):
                t_name = item.get("topic", "")
                t_slug = item.get("slug") or t_name.lower().replace(" ", "-")
                t_score = float(item.get("score", 70.0))
                t_seen = int(item.get("problems_seen", 1))

                topic = Topic.query.filter_by(slug=t_slug).first()
                if not topic:
                    topic = Topic(name=t_name, slug=t_slug)
                    db.session.add(topic)
                    db.session.flush()

                skill = SkillScore.query.filter_by(user_id=user_id, topic_id=topic.id).first()
                if not skill:
                    skill = SkillScore(
                        user_id=user_id,
                        topic_id=topic.id,
                        score=t_score,
                        confidence=min(1.0, t_seen / 5.0),
                        problems_seen=t_seen,
                        last_updated=datetime.now(timezone.utc)
                    )
                    db.session.add(skill)
                else:
                    skill.score = round(0.5 * t_score + 0.5 * skill.score, 1)
                    skill.problems_seen = max(skill.problems_seen, t_seen)
                    skill.confidence = min(1.0, skill.problems_seen / 5.0)
                    skill.last_updated = datetime.now(timezone.utc)

            record.content = json.dumps(report_data)
            record.model_used = model_used
            record.status = "done"
            record.submissions_hash = sub_hash
            record.generated_at = datetime.now(timezone.utc)
            db.session.commit()
            logger.info("Report completed and skill scores synchronized for user %d using %s", user_id, model_used)

        except Exception as exc:
            logger.exception("AI report generation failed for user %d", user_id)
            try:
                record = (
                    AIReport.query.filter_by(user_id=user_id, status="pending")
                    .order_by(AIReport.created_at.desc())
                    .first()
                )
                if record:
                    user = db.session.get(User, user_id)
                    fallback_report = _rule_based_report(user, [])
                    record.content = json.dumps(fallback_report)
                    record.model_used = "dsa-performance-engine (fallback)"
                    record.status = "done"
                    record.generated_at = datetime.now(timezone.utc)
                    db.session.commit()
            except Exception:
                db.session.rollback()


def _rule_based_report(user, submissions, evaluations=None) -> dict:
    """High-fidelity algorithmic DSA evaluation when AI API is unavailable or offline."""
    total = len(submissions)
    langs = {}
    for s in submissions:
        langs[s.language] = langs.get(s.language, 0) + 1
    top_lang = max(langs, key=langs.get) if langs else "Python"

    wrong_counts = [s.wrong_attempts for s in submissions]
    avg_wrong = sum(wrong_counts) / len(wrong_counts) if wrong_counts else 0

    all_patterns = []
    topic_data = {}
    for s in submissions:
        ev = s.evaluation or (next((e for e in evaluations if e.submission_id == s.id), None) if evaluations else None)
        if ev:
            if ev.detected_patterns:
                try:
                    all_patterns.extend(json.loads(ev.detected_patterns))
                except Exception:
                    pass
            if ev.detected_topics:
                try:
                    sub_topics = json.loads(ev.detected_topics)
                    score_val = ev.overall_score or 75.0
                    for top in sub_topics:
                        if top not in topic_data:
                            topic_data[top] = {"scores": [], "count": 0}
                        topic_data[top]["scores"].append(score_val)
                        topic_data[top]["count"] += 1
                except Exception:
                    pass

    pattern_freq = {}
    for p in all_patterns:
        pattern_freq[p] = pattern_freq.get(p, 0) + 1
    top_patterns = sorted(pattern_freq, key=pattern_freq.get, reverse=True)[:4]

    strengths = []
    weaknesses = []
    if total >= 1:
        strengths.append(f"Successfully solved {total} problem(s) in {top_lang.upper()} with clean execution")
    if avg_wrong == 0:
        strengths.append("Exceptional first-pass accuracy (0 wrong attempts recorded)")
    elif avg_wrong <= 1.0:
        strengths.append("High first-attempt success rate with minimal penalty attempts")
    else:
        weaknesses.append("Average of >1 wrong attempt per problem: test edge cases before submitting")

    if top_patterns:
        strengths.append(f"Strong algorithmic affinity with {', '.join([p.replace('-', ' ').title() for p in top_patterns[:2]])}")
    else:
        weaknesses.append("Pattern repertoire is currently early stage; practice classical patterns like Two Pointers and Sliding Window")

    if total < 5:
        weaknesses.append(f"Low submission volume ({total} problem(s)); solve at least 15-20 problems across diverse topics for placement readiness")

    topic_scores = []
    for slug, d in topic_data.items():
        avg_s = round(sum(d["scores"]) / len(d["scores"]), 1)
        name = slug.replace("-", " ").title()
        topic_scores.append({
            "topic": name,
            "slug": slug,
            "score": avg_s,
            "problems_seen": d["count"],
            "feedback": f"Demonstrated competency in {name} with {d['count']} problem(s)."
        })

    if not topic_scores:
        topic_scores.append({
            "topic": "Arrays & Hashing",
            "slug": "arrays-and-hashing",
            "score": 75.0,
            "problems_seen": total or 1,
            "feedback": "Core foundational arrays and lookup mastery."
        })

    overall_dsa_score = round(
        sum(t["score"] * t["problems_seen"] for t in topic_scores) /
        max(1, sum(t["problems_seen"] for t in topic_scores)), 1
    )
    skill_level = _skill_label(overall_dsa_score, min(1.0, total / 5.0))

    recommendations = [
        {"topic": "Two Pointers", "reason": "Standard technique for array traversal and search with O(1) space", "priority": "high"},
        {"topic": "Binary Search", "reason": "Essential for logarithmic search and rotated array problems", "priority": "high"},
        {"topic": "Dynamic Programming", "reason": "High weightage in tier-1 technical interviews and online assessments", "priority": "medium"},
        {"topic": "Trees & Graphs", "reason": "Core foundation for recursive thinking and hierarchical data traversal", "priority": "medium"},
    ]

    return {
        "strengths": strengths or ["Consistent problem solving initiative"],
        "weaknesses": weaknesses or ["Expand problem diversity across unseen DSA categories"],
        "skill_summary": f"Demonstrated solid algorithmic foundation with {total} solved problem(s) in {top_lang}. Current overall DSA proficiency is {skill_level} ({overall_dsa_score}/100).",
        "top_patterns": [p.replace("-", " ").title() for p in top_patterns] or ["Arrays & Hash Maps"],
        "overall_dsa_score": overall_dsa_score,
        "skill_level": skill_level,
        "topic_scores": topic_scores,
        "recommendations": recommendations,
        "learning_path": [
            "Arrays & Hashing", "Two Pointers", "Sliding Window",
            "Stacks & Queues", "Binary Search", "Linked Lists",
            "Trees & BST", "Heaps", "Graphs (BFS/DFS)", "Dynamic Programming"
        ],
        "weekly_target": "Solve 5 problems covering at least 2 distinct topics",
        "encouragement": f"Solid progress! Every problem you analyze builds long-term algorithmic intuition.",
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


@app.route("/api/auth/auto-login", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def auto_login():
    """Seamless auto-login for Chrome Extension & local dashboard.
    Returns existing active user session, or auto-initializes the default learner account.
    """
    body = json_body() if (request.is_json and request.method == "POST") else {}
    target_email = clean_string(body.get("email"), 255).lower() if body else ""

    if target_email:
        user = User.query.filter_by(email=target_email).first()
    else:
        user = User.query.order_by(User.id.asc()).first()

    if not user:
        # Create default learner user for seamless first-time onboarding
        default_email = target_email or "sahil98099@gmail.com"
        user = User(
            email=default_email,
            name="Sahil",
            password_hash=generate_password_hash("password123"),
        )
        db.session.add(user)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            user = User.query.first()

    if not user:
        return jsonify({"error": "Unable to initialize user account."}), 500

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


def build_problem_list_with_evaluations(latest):
    problems = []
    for s in latest:
        ev = s.evaluation or Evaluation.query.filter_by(submission_id=s.id).first()
        if not ev or not ev.ai_thought or not ev.expected_solution:
            try:
                analysis = analyze_solution_with_ai(s, s.problem)
                if not ev:
                    ev = Evaluation(submission_id=s.id)
                    db.session.add(ev)
                ev.time_complexity = analysis.get("time_complexity")
                ev.space_complexity = analysis.get("space_complexity")
                ev.expected_time_complexity = analysis.get("expected_time_complexity")
                ev.expected_space_complexity = analysis.get("expected_space_complexity")
                ev.is_optimal = analysis.get("is_optimal", True)
                ev.ai_thought = analysis.get("ai_thought", "")
                ev.expected_solution = analysis.get("expected_solution", "")
                ev.status = "done"
                ev.evaluated_at = datetime.now(timezone.utc)
                db.session.commit()
            except Exception as e:
                logger.warning("Auto evaluation failed for submission %d: %s", s.id, e)

        problems.append({
            "id": s.problem.id,
            "title": s.problem.title,
            "slug": s.problem.slug,
            "url": s.problem.url,
            "correct": s.right_attempts,
            "wrong": s.wrong_attempts,
            "attempts": s.total_attempts,
            "accuracy": accuracy_of(s.right_attempts, s.total_attempts),
            "last_solved_at": as_utc(s.submitted_at).isoformat(),
            "time_complexity": (ev.time_complexity if ev and ev.time_complexity else "O(n)"),
            "space_complexity": (ev.space_complexity if ev and ev.space_complexity else "O(1)"),
            "expected_time_complexity": (ev.expected_time_complexity if ev and ev.expected_time_complexity else "O(n)"),
            "expected_space_complexity": (ev.expected_space_complexity if ev and ev.expected_space_complexity else "O(1)"),
            "is_optimal": (ev.is_optimal if ev and ev.is_optimal is not None else True),
        })
    return problems


@app.get("/api/dashboard/summary")
@jwt_required()
def dashboard_summary():
    latest = latest_successes_for_user(user_id_from_token())

    right = sum(s.right_attempts for s in latest)
    wrong = sum(s.wrong_attempts for s in latest)
    total = sum(s.total_attempts for s in latest)

    problems = build_problem_list_with_evaluations(latest)

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
    ev = latest.evaluation or Evaluation.query.filter_by(submission_id=latest.id).first()
    if not ev or not ev.ai_thought or not ev.expected_solution:
        try:
            analysis = analyze_solution_with_ai(latest, problem)
            if not ev:
                ev = Evaluation(submission_id=latest.id)
                db.session.add(ev)
            ev.time_complexity = analysis.get("time_complexity")
            ev.space_complexity = analysis.get("space_complexity")
            ev.expected_time_complexity = analysis.get("expected_time_complexity")
            ev.expected_space_complexity = analysis.get("expected_space_complexity")
            ev.is_optimal = analysis.get("is_optimal", True)
            ev.ai_thought = analysis.get("ai_thought", "")
            ev.expected_solution = analysis.get("expected_solution", "")
            ev.status = "done"
            ev.evaluated_at = datetime.now(timezone.utc)
            db.session.commit()
        except Exception as e:
            logger.warning("Auto evaluation failed for problem detail %s: %s", slug, e)

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
        "evaluation": {
            "time_complexity": ev.time_complexity if ev else "O(n)",
            "space_complexity": ev.space_complexity if ev else "O(1)",
            "expected_time_complexity": ev.expected_time_complexity if ev else "O(n)",
            "expected_space_complexity": ev.expected_space_complexity if ev else "O(1)",
            "is_optimal": ev.is_optimal if (ev and ev.is_optimal is not None) else True,
            "ai_thought": ev.ai_thought if ev else "",
            "expected_solution": ev.expected_solution if ev else "",
            "overall_score": ev.overall_score if ev else 80.0,
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


@app.post("/api/problems/<slug>/analyze")
@jwt_required()
def analyze_problem_solution(slug):
    slug = clean_string(slug, 500).lower()
    uid = user_id_from_token()

    problem = Problem.query.filter_by(slug=slug).first()
    if not problem:
        return jsonify({"error": "Problem not found."}), 404

    sub = (
        Submission.query
        .filter_by(user_id=uid, problem_id=problem.id)
        .order_by(Submission.submitted_at.desc(), Submission.id.desc())
        .first()
    )
    if not sub:
        return jsonify({"error": "No submission found for this problem."}), 404

    analysis = analyze_solution_with_ai(sub, problem)
    ev = Evaluation.query.filter_by(submission_id=sub.id).first()
    if not ev:
        ev = Evaluation(submission_id=sub.id)
        db.session.add(ev)

    ev.time_complexity = analysis.get("time_complexity")
    ev.space_complexity = analysis.get("space_complexity")
    ev.expected_time_complexity = analysis.get("expected_time_complexity")
    ev.expected_space_complexity = analysis.get("expected_space_complexity")
    ev.is_optimal = analysis.get("is_optimal", True)
    ev.ai_thought = analysis.get("ai_thought", "")
    ev.expected_solution = analysis.get("expected_solution", "")
    ev.status = "done"
    ev.evaluated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        "success": True,
        "evaluation": {
            "time_complexity": ev.time_complexity,
            "space_complexity": ev.space_complexity,
            "expected_time_complexity": ev.expected_time_complexity,
            "expected_space_complexity": ev.expected_space_complexity,
            "is_optimal": ev.is_optimal,
            "ai_thought": ev.ai_thought,
            "expected_solution": ev.expected_solution,
            "overall_score": ev.overall_score,
        }
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

    # If no skill records yet but user has submissions, auto-generate
    if not scores:
        has_sub = Submission.query.filter_by(user_id=uid, verdict="Accepted").first()
        if has_sub:
            generate_ai_report(uid, force=False)
            scores = (
                SkillScore.query
                .filter_by(user_id=uid)
                .options(joinedload(SkillScore.topic))
                .order_by(SkillScore.score.desc())
                .all()
            )

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
            "label": _skill_label(s.score, s.confidence),
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
        "skill_level": _skill_label(overall, 1.0 if skill_list else 0.0),
        "topics": skill_list,
    })


@app.post("/api/skills/analyze")
@jwt_required()
def analyze_skills_ai():
    """Trigger AI analysis to evaluate student performance and calculate overall DSA skill."""
    uid = user_id_from_token()
    generate_ai_report(uid, force=True)
    return get_skill_scores()


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

    problems = build_problem_list_with_evaluations(latest)

    # Skill scores
    skill_scores = (
        SkillScore.query
        .filter_by(user_id=uid)
        .options(joinedload(SkillScore.topic))
        .order_by(SkillScore.score.desc())
        .all()
    )
    if not skill_scores and latest:
        generate_ai_report(uid, force=False)
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
            "skill_level": _skill_label(overall_skill, 1.0 if skill_scores else 0.0),
            "streak_days": streak,
        },
        "problems": problems,
        "topics": topics,
        "report_status": report_status,
    })


def _skill_label(score: float, confidence: float) -> str:
    if confidence < 0.1:
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


def auto_evaluate_existing():
    """Ensure existing submissions have evaluations and reports populated."""
    with app.app_context():
        try:
            subs = Submission.query.all()
            for s in subs:
                ev = Evaluation.query.filter_by(submission_id=s.id).first()
                if not ev or ev.status != "done":
                    evaluate_submission(s.id)
            users = User.query.all()
            for u in users:
                has_sub = Submission.query.filter_by(user_id=u.id, verdict="Accepted").first()
                has_rep = AIReport.query.filter_by(user_id=u.id, status="done").first()
                if has_sub and not has_rep:
                    generate_ai_report(u.id, force=False)
        except Exception as e:
            logger.warning("auto_evaluate_existing warning: %s", e)


# Run auto-eval on startup if in development
if not IS_PROD:
    try:
        auto_evaluate_existing()
    except Exception:
        pass

# Run (development only; use Gunicorn in production)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
