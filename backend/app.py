import os
import secrets
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    get_jwt_identity,
    jwt_required,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)

# Serve the dashboard from the same Flask server during local development.
# In production, DASHBOARD_URL can point to a separately hosted frontend.
DASHBOARD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard"))

@app.get("/dashboard")
@app.get("/dashboard/")
def dashboard_home():
    return send_from_directory(DASHBOARD_DIR, "index.html")

@app.get("/dashboard/<path:filename>")
def dashboard_files(filename):
    return send_from_directory(DASHBOARD_DIR, filename)

database_url = os.getenv("DATABASE_URL", "sqlite:///learnsense.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)

app.config.update(
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY", "dev-only-change-me"),
    JWT_ACCESS_TOKEN_EXPIRES=timedelta(days=int(os.getenv("JWT_ACCESS_DAYS", "30"))),
)

db = SQLAlchemy(app)
jwt = JWTManager(app)

# Development-friendly CORS. Set DASHBOARD_ORIGIN in production.
dashboard_origin = os.getenv("DASHBOARD_ORIGIN", "*")
CORS(app, resources={r"/api/*": {"origins": dashboard_origin}})


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Problem(db.Model):
    __tablename__ = "problems"
    id = db.Column(db.Integer, primary_key=True)
    leetcode_id = db.Column(db.Integer, nullable=True)
    title = db.Column(db.String(500), nullable=False)
    slug = db.Column(db.String(500), unique=True, nullable=False, index=True)
    url = db.Column(db.Text, nullable=False)


class Submission(db.Model):
    """Only successful submissions are stored remotely.

    right_attempts/wrong_attempts/total_attempts are the counters calculated by
    the extension at the moment the Accepted submission is recorded.
    """
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
    submitted_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = db.relationship("User", backref=db.backref("submissions", lazy=True))
    problem = db.relationship("Problem", backref=db.backref("submissions", lazy=True))


class DashboardCode(db.Model):
    """One-time extension -> website handoff code. Never put JWTs in URLs."""
    __tablename__ = "dashboard_codes"
    id = db.Column(db.Integer, primary_key=True)
    code_hash = db.Column(db.String(128), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)


def now_utc():
    return datetime.utcnow()


def user_id_from_token():
    return int(get_jwt_identity())


def user_json(user):
    return {"id": user.id, "email": user.email, "name": user.name}


def parse_timestamp(value):
    try:
        return datetime.utcfromtimestamp(float(value) / 1000)
    except (ValueError, TypeError, OverflowError):
        return now_utc()


def hash_code(code):
    # SHA-256 is enough for a short-lived random one-time code.
    import hashlib
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "LearnSense API"})


@app.post("/api/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    name = str(data.get("name", "")).strip() or None

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists."}), 409

    user = User(email=email, name=name, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user_json(user)}), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    user = User.query.filter_by(email=email).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password."}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user_json(user)})


@app.get("/api/me")
@jwt_required()
def me():
    user = db.session.get(User, user_id_from_token())
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify(user_json(user))


@app.post("/api/auth/dashboard-code")
@jwt_required()
def create_dashboard_code():
    """Create a short-lived, one-use code for opening the hosted dashboard."""
    raw = secrets.token_urlsafe(32)
    record = DashboardCode(
        code_hash=hash_code(raw),
        user_id=user_id_from_token(),
        expires_at=now_utc() + timedelta(minutes=2),
    )
    db.session.add(record)
    db.session.commit()
    dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:5000/dashboard").rstrip("/")
    return jsonify({"url": f"{dashboard_url}/extension-login.html?code={raw}"})


@app.post("/api/auth/exchange-dashboard-code")
def exchange_dashboard_code():
    data = request.get_json(silent=True) or {}
    raw = str(data.get("code", "")).strip()
    if not raw:
        return jsonify({"error": "Code is required."}), 400

    record = DashboardCode.query.filter_by(code_hash=hash_code(raw)).first()
    if not record or record.used_at or record.expires_at < now_utc():
        return jsonify({"error": "Dashboard code is invalid or expired."}), 401

    record.used_at = now_utc()
    db.session.commit()

    token = create_access_token(identity=str(record.user_id))
    return jsonify({"access_token": token})


@app.post("/api/submissions")
@jwt_required()
def create_submission():
    """Accept ONLY a successful submission and its counters/code."""
    data = request.get_json(silent=True) or {}
    verdict = str(data.get("verdict", "")).strip()

    if verdict != "Accepted":
        return jsonify({"error": "Only Accepted submissions are stored remotely."}), 400

    title = str(data.get("title", "")).strip() or "Untitled problem"
    slug = str(data.get("problemSlug", "")).strip()
    url = str(data.get("problemUrl", "")).strip()
    code = str(data.get("code", ""))
    language = str(data.get("lang", "unknown")).strip() or "unknown"

    try:
        right_attempts = max(1, int(data.get("rightAttempts", 1)))
        wrong_attempts = max(0, int(data.get("wrongAttempts", 0)))
        total_attempts = max(1, int(data.get("totalAttempts", right_attempts + wrong_attempts)))
    except (ValueError, TypeError):
        return jsonify({"error": "Attempt counters must be integers."}), 400

    if not slug or not url:
        return jsonify({"error": "problemSlug and problemUrl are required."}), 400
    if total_attempts != right_attempts + wrong_attempts:
        return jsonify({"error": "totalAttempts must equal rightAttempts + wrongAttempts."}), 400

    problem = Problem.query.filter_by(slug=slug).first()
    if not problem:
        problem = Problem(title=title, slug=slug, url=url)
        db.session.add(problem)
        db.session.flush()
    else:
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
        submitted_at=parse_timestamp(data.get("timestamp")),
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
    latest = latest_successes_for_user(user_id_from_token())

    right = sum(s.right_attempts for s in latest)
    wrong = sum(s.wrong_attempts for s in latest)
    total = sum(s.total_attempts for s in latest)

    problems = []
    for s in latest:
        problems.append({
            "id": s.problem.id,
            "title": s.problem.title,
            "slug": s.problem.slug,
            "url": s.problem.url,
            "correct": s.right_attempts,
            "wrong": s.wrong_attempts,
            "attempts": s.total_attempts,
            "accuracy": round(s.right_attempts / s.total_attempts * 100) if s.total_attempts else 0,
            "last_solved_at": s.submitted_at.isoformat(),
        })

    problems.sort(key=lambda x: x["last_solved_at"], reverse=True)
    return jsonify({
        "overall": {
            "solved_problems": len(latest),
            "correct": right,
            "wrong": wrong,
            "total": total,
            "accuracy": round(right / total * 100) if total else 0,
        },
        "problems": problems,
    })


@app.get("/api/problems/<slug>")
@jwt_required()
def problem_detail(slug):
    user_id = user_id_from_token()
    problem = Problem.query.filter_by(slug=slug).first()
    if not problem:
        return jsonify({"error": "Problem not found."}), 404

    submissions = (
        Submission.query
        .filter_by(user_id=user_id, problem_id=problem.id)
        .order_by(Submission.submitted_at.desc())
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
            "accuracy": round(latest.right_attempts / latest.total_attempts * 100) if latest.total_attempts else 0,
        },
        "submissions": [
            {
                "id": s.id,
                "verdict": s.verdict,
                "language": s.language,
                "submitted_at": s.submitted_at.isoformat(),
                "code": s.code,
                "right_attempts": s.right_attempts,
                "wrong_attempts": s.wrong_attempts,
                "total_attempts": s.total_attempts,
            }
            for s in submissions
        ],
    })


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)
