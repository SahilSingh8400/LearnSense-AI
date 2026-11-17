# PROJECT REPORT: LEARNSENSE AI
## Intelligent DSA Learning Analytics & Automated Code Evaluation System

---

**Project Title:** LearnSense AI — Chrome MV3 Extension, Flask Backend & Analytics Dashboard  
**Academic Year / Submission Cycle:** 2026  
**Document Version:** 1.0 (Comprehensive Project Submission File)  
**Repository Structure:** Extension (Client) | Backend (Flask REST API + PostgreSQL) | Dashboard (Web SPA) | Analyze (WIP Module)  

---

## TABLE OF CONTENTS
1. [Executive Summary & Abstract](#1-executive-summary--abstract)
2. [Problem Statement & Motivation](#2-problem-statement--motivation)
3. [System Architecture & Data Flow](#3-system-architecture--data-flow)
4. [Complete Implementation Breakdown (What Has Been Built)](#4-complete-implementation-breakdown-what-has-been-built)
   - 4.1. Browser Extension (Chrome/Brave Manifest V3)
   - 4.2. Backend REST API & Middleware
   - 4.3. Algorithmic DSA Evaluation & Heuristic Engine
   - 4.4. AI Learning Coach & OpenRouter Integration
   - 4.5. Web Analytics Dashboard
   - 4.6. Database Design & Relational Schema
   - 4.7. DevOps, Deployment & Infrastructure
5. [Pending, Partial & Future Roadmap (What Is Not Yet Fully Implemented)](#5-pending-partial--future-roadmap-what-is-not-yet-fully-implemented)
   - 5.1. The `Analyze` Module & OCR / Computer Vision Pipeline
   - 5.2. Multi-Platform Support (Codeforces, HackerRank, GFG)
   - 5.3. Dynamic Sandbox Execution vs. Static Heuristics
   - 5.4. Real-Time In-Editor AI Copilot / Hint Engine
   - 5.5. Social Cohorts, Leaderboards & Peer Comparison
   - 5.6. Spaced Repetition Revision Scheduler
6. [Feature Status Matrix (Implemented vs. In-Progress vs. Planned)](#6-feature-status-matrix)
7. [API Specification & Endpoints](#7-api-specification--endpoints)
8. [Database Schema Dictionary](#8-database-schema-dictionary)
9. [Security, Performance & Architectural Decisions](#9-security-performance--architectural-decisions)
10. [Hardware, Software & Environment Requirements](#10-hardware-software--environment-requirements)
11. [Conclusion & Academic Summary](#11-conclusion--academic-summary)

---

## 1. EXECUTIVE SUMMARY & ABSTRACT

### 1.1 Abstract
**LearnSense AI** is an intelligent learning telemetry and performance analytics ecosystem designed for students and software engineering candidates preparing for technical interviews on LeetCode. Traditional competitive programming platforms inform users *whether* their submission passed or failed, but they provide zero structured feedback on algorithmic efficiency, recurring anti-patterns, topic mastery, or personalized roadmaps.

To solve this, LearnSense AI implements an end-to-end distributed system comprising:
1. A **Manifest V3 Chromium Browser Extension** that passively monitors LeetCode submissions, extracts source code directly from the underlying Monaco editor instance, and maintains accurate local attempt counters.
2. A **Python Flask Backend REST API** running on Gunicorn with a PostgreSQL database, enforcing secure JWT authentication and single-use cryptographic dashboard tokens.
3. An **Automated DSA Evaluation Engine** that applies pattern detection, heuristic complexity estimation ($O(1)$ to $O(2^n)$), and a 5-dimension scoring algorithm (Correctness, Approach, Complexity, Optimization, and Coverage).
4. An **AI-Powered Learning Coach** (powered by OpenRouter / LLMs with a deterministic rule-based fallback) that generates personalized study reports, identifies weaknesses, and prescribes targeted practice targets.
5. A **Responsive Web Dashboard** featuring visual skill radar scores, topic mastery distributions, attempt breakdowns, day streak tracking, and interactive historical code inspection.

---

## 2. PROBLEM STATEMENT & MOTIVATION

### 2.1 The Problem
When practicing Data Structures and Algorithms (DSA):
- **Hidden Attempt Friction:** Platforms like LeetCode display the final "Accepted" submission, but hide the true cognitive friction—the number of failed attempts (Time Limit Exceeded, Wrong Answers, Memory Limit Exceeded) before getting it right.
- **Surface-Level Feedback:** LeetCode runtimes fluctuate based on server load and do not mathematically break down whether a solution utilized an optimal approach (e.g., $O(n)$ Sliding Window vs. $O(n^2)$ nested brute force).
- **Lack of Topic-Wise Mastery Telemetry:** Students have no centralized dashboard showing their Exponential Moving Average (EMA) skill score across core algorithmic patterns like Two Pointers, Dynamic Programming, Graphs, and Heaps.
- **Privacy & Token Leakage Concerns:** Traditional browser extensions often leak long-lived JWTs via URL query parameters when navigating users to an external dashboard.

### 2.2 The LearnSense AI Solution
LearnSense AI bridges the gap between problem-solving and actionable learning. It captures every trial locally in browser storage, sends *only verified accepted solutions* along with aggregated attempt counters to the cloud API, computes objective skill scores, and serves an intuitive analytics portal.

---

## 3. SYSTEM ARCHITECTURE & DATA FLOW

### 3.1 Architectural Diagram
```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       BROWSER CLIENT (LeetCode Page)                        │
│                                                                             │
│  [Page Inject Script]  <-- window.postMessage -->  [Content Script (MV3)]   │
│  (Extracts Monaco AST/Code)                        (Watches DOM Verdicts)   │
│                                                              │              │
│                                           Tracks ALL attempts│ (local)      │
│                                                              ▼              │
│                                                   [chrome.storage.local]    │
│                                                              │              │
│                                            ONLY Accepted Subs▼              │
└──────────────────────────────────────────────────────────────┼──────────────┘
                                                               │ HTTPS REST
                                                               │ (Bearer JWT)
                                                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        LEARNSENSE FLASK BACKEND API                         │
│                                                                             │
│  ├── Auth & Rate Limiting (Flask-JWT-Extended, Flask-Limiter)               │
│  ├── Submission Ingestion Engine (/api/submissions)                         │
│  ├── Heuristic DSA Evaluator (Complexity, Pattern Detection, Multi-Score)   │
│  ├── Async Background Thread Dispatcher (Evaluation & AI Report)            │
│  └── Single-Use Token Handoff (/api/auth/dashboard-code)                    │
└───────────────────────────────┬──────────────────────────────┬──────────────┘
                                │                              │
                Database Queries│                LLM Prompt API│ (OpenRouter)
                                ▼                              ▼
┌───────────────────────────────────────────────┐  ┌──────────────────────────┐
│             MANAGED POSTGRESQL                │  │    OPENROUTER AI API     │
│  (Users, Problems, Submissions, Evaluations,  │  │   (Gemma 3 27B / Fallback│
│   Topics, SkillScores, AIReports, UserGoals)  │  │    Structured JSON)      │
└───────────────────────────────────────────────┘  └──────────────────────────┘
                                ▲
                                │ REST Data Fetch
                                │ (Exchanged Session Token)
┌───────────────────────────────┴─────────────────────────────────────────────┐
│                        HOSTED ANALYTICS DASHBOARD                           │
│                         (Vanilla HTML5 / CSS3 / JS)                         │
│                                                                             │
│  ├── Tab 1: Overview & Hero Score (DSA Skill, Day Streak, Attempt Accuracy) │
│  ├── Tab 2: DSA Skill Map (Per-topic mastery bars & confidence ratings)     │
│  ├── Tab 3: AI Learning Report (Personalized strengths, weaknesses, paths)  │
│  ├── Tab 4: All Problems Catalog (History table with Monaco Code Viewer)    │
│  └── Tab 5: Goal Setting (Interview prep targets & daily study timers)      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow Lifecycle
1. **User Solves Problem:** When the user clicks "Submit" on LeetCode, `content.js` initiates a DOM `MutationObserver`.
2. **Code Extraction:** `content.js` queries `page-inject.js` via `window.postMessage`. Because `page-inject.js` runs in the main page execution context, it accesses `window.monaco.editor.getModels()[0].getValue()`, bypassing DOM virtualization truncations.
3. **Local Telemetry:** If the submission is "Wrong Answer" or "TLE", the attempt counter for that problem increments in `chrome.storage.local`.
4. **Cloud Transmission:** Once the verdict is **Accepted**, the extension packages the problem metadata, attempt counters (`rightAttempts`, `wrongAttempts`, `totalAttempts`), and code, dispatching it to `POST /api/submissions`.
5. **Asynchronous Evaluation:** The backend writes the submission, then spins up background daemon threads to compute heuristic complexity and update the user's per-topic skill scores using an Exponential Moving Average ($\alpha = 0.4$).
6. **AI Synthesis:** If submission milestones are reached, the AI engine calls OpenRouter to generate structured feedback or generates a deterministic fallback report.
7. **Secure Dashboard Handoff:** Clicking "View Dashboard" generates an ephemeral, single-use, 2-minute cryptographic hash token (`/api/auth/dashboard-code`), ensuring zero credential exposure in browser history.

---

## 4. COMPLETE IMPLEMENTATION BREAKDOWN (WHAT HAS BEEN BUILT)

### 4.1 Browser Extension (`extension/`)
- **Manifest V3 Architecture:** Built to standard Chromium MV3 guidelines utilizing a background service worker (`background.js`).
- **Main-World Page Injection (`page-inject.js`):** Injected directly into the document DOM to interface with LeetCode’s internal Monaco editor instance.
- **Robust DOM Mutation Observer (`content.js`):** Actively listens for verdict nodes (`Accepted`, `Wrong Answer`, `Time Limit Exceeded`, `Runtime Error`, `Memory Limit Exceeded`) with timeout guards.
- **Popup UI (`popup.html`, `popup.js`, `popup.css`):**
  - Instant login/signup tab switcher with JWT validation.
  - Live local stats card (Correct count, Wrong count, Success percentage).
  - DSA Skill Score and Day Streak badge sync.
  - Recent submissions carousel with syntax-ready code preview.
  - "Reset Local" debugging tool and "View Dashboard" direct-launcher.

### 4.2 Backend API & Security Architecture (`backend/app.py`)
- **Flask 3.x Framework:** Structured modular API with environment-driven production/development switching.
- **JWT Authentication Lifecycle:**
  - `POST /api/auth/register`: Password complexity verification (minimum 8 characters, maximum 256), email regex validation, and bcrypt hashing (`generate_password_hash`).
  - `POST /api/auth/login`: Constant-time hash verification against dummy hashes to eliminate user enumeration timing attacks.
  - `POST /api/auth/refresh`: Issues fresh access tokens using long-lived refresh tokens.
  - `GET /api/me`: Returns profile payload.
- **Rate Limiting & Protection (Flask-Limiter):**
  - Registration capped at 5 per hour.
  - Login capped at 10 requests/minute per IP and 5 requests/minute per email bucket to prevent credential stuffing.
  - Submissions capped at 120 per hour.
- **CORS & Origin Hardening:** Strict dynamic CORS headers validating explicit `chrome-extension://` IDs in production, denying untrusted extensions.
- **Security Headers:** Enforced `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Cache-Control: no-store` on all API routes.

### 4.3 Algorithmic DSA Evaluation & Heuristic Engine
The backend implements a multi-dimensional heuristic evaluation engine that scores code across 5 weighted axes:
$$\text{Overall Score} = \frac{\sum (\text{Dimension Score} \times \text{Weight})}{\sum \text{Weights}}$$

- **Weights Configured:**
  - Correctness Weight: $0.25$
  - Approach Quality Weight: $0.30$
  - Complexity Efficiency Weight: $0.20$
  - Code Optimization Weight: $0.15$
  - Topic Coverage Weight: $0.10$

- **Pattern Detection:** Identifies 20 distinct DSA paradigms via keyword and structural token matching:
  - *Two Pointers, Sliding Window, Dynamic Programming, Binary Search, Breadth-First Search (BFS), Depth-First Search (DFS), Hash Maps, Heaps/Priority Queues, Greedy, Divide and Conquer, Graphs, Trees, Monotonic Stacks, Backtracking, Sorting, Bit Manipulation, Math, String Manipulation, Linked Lists, and Interval Processing.*
- **Static Complexity Estimator:**
  - Evaluates loop nesting levels (`for`, `while`) and recursive calls (`dfs`, `solve`, `backtrack`, `helper`).
  - Predicts Time Complexity: $O(1)$, $O(\log n)$, $O(n)$, $O(n \log n)$, $O(n^2)$, or $O(2^n)$.
  - Predicts Space Complexity: $O(1)$ vs $O(n)$ by inspecting dynamic data allocations (`dict`, `set`, `list`, `defaultdict`).
- **Dynamic Topic Skill Scoring:**
  - Applies an **Exponential Moving Average (EMA)** with smoothing factor $\alpha = 0.4$:
    $$\text{Score}_{\text{new}} = 0.4 \times \text{Overall}_{\text{submission}} + 0.6 \times \text{Score}_{\text{prev}}$$
  - Computes a Confidence Rating based on sample size: $\text{Confidence} = \min(1.0, \frac{\text{Problems Seen}}{5.0})$.
  - Categorizes students into proficiency tiers: *Provisional, Novice, Beginner, Developing, Proficient, Expert*.

### 4.4 AI Learning Coach (`backend/app.py`)
- **LLM Ingestion via OpenRouter:** Configured to invoke high-parameter instruction models (e.g., `google/gemma-3-27b-it:free`).
- **Structured JSON Synthesis:** Prompts the model to return strict JSON covering:
  - Key student strengths and weaknesses based on empirical attempts.
  - Dominant algorithmic patterns utilized.
  - Prioritized topic recommendations (High/Medium/Low priority with rationales).
  - Recommended sequential learning path.
  - Specific weekly practice target and motivational encouragement.
- **Deterministic Rule-Based Fallback:** If the external AI API is unreachable or no API key is provided, a native rule-based analytics engine analyzes submission frequency, language comfort, and error distributions to synthesize a complete report.
- **Idempotent Caching:** Submissions are fingerprinted using SHA-256 hashes to prevent redundant, expensive LLM calls if the user's problem set has not changed.

### 4.5 Web Analytics Dashboard (`dashboard/`)
- **Zero-Build Vanilla Web Architecture:** Fully responsive, modern CSS3 and vanilla ES6+ JavaScript requiring no build step (Vite/Webpack), ensuring instantaneous deployment and zero dependency drift.
- **Secure Code Exchange (`extension-login.html`):** Intercepts the one-use hash code from the extension, exchanges it for JWT credentials via `POST /api/auth/exchange-dashboard-code`, and cleanses the URL bar.
- **Multi-Tab Interface:**
  1. **Overview Tab:** Hero score ring, consecutive day streak indicator, attempt accuracy meters, and interactive problem list.
  2. **DSA Skill Map Tab:** Topic mastery visual meters, problems solved per topic, and statistical confidence bars.
  3. **AI Report Tab:** Formatted cards displaying strengths, critical gaps, tailored curriculum, and a manual "Regenerate" trigger.
  4. **Problems Tab:** Searchable, sortable list of all solved LeetCode challenges.
  5. **Goals Tab:** Interactive goal configuration (Job Placement, University Exams, General Upskilling) with target completion dates and daily minute quotas.
- **Built-In Code Viewer:** Clicking any problem in the dashboard loads the exact accepted solution submitted by the student with metadata.

### 4.6 Relational Database Schema (`PostgreSQL / SQLite`)
Models implemented via SQLAlchemy ORM:
- `User`: Accounts, hashed credentials, and creation timestamps.
- `Problem`: Normalized catalog of LeetCode challenges (title, slug, URL).
- `Submission`: Records accepted solutions, languages, right/wrong/total attempts, and submission timestamps.
- `DashboardCode`: Ephemeral, hashed tokens with expiry timestamps for passwordless extension-to-dashboard authentication.
- `Topic`: DSA taxonomy reference table (e.g., dynamic-programming, graphs, trees).
- `SkillScore`: Per-user, per-topic score with confidence metric and problem counter.
- `Evaluation`: Static analysis output for each submission (correctness, complexity, detected patterns).
- `AIReport`: Persistent store of generated coach reports and cache hashes.
- `UserGoal`: User study targets, interview deadlines, and daily minute targets.

### 4.7 DevOps & Deployment Infrastructure
- **Render Infrastructure-as-Code (`render.yaml`):** Configures PostgreSQL instance and Gunicorn web service with environment variables.
- **Database Migrations:** Configured using Alembic and Flask-Migrate (`backend/migrations/`) to ensure schema version control across deployments.
- **Production Guide (`DEPLOYMENT.md`):** Complete 570-line operational handbook detailing setup, CORS configuration, Render deployment, and Chrome Web Store publishing.

---

## 5. PENDING, PARTIAL & FUTURE ROADMAP (WHAT IS NOT YET FULLY IMPLEMENTED)

While the core LearnSense AI pipeline (Extension $\to$ API $\to$ Evaluator $\to$ Dashboard) is fully operational, several planned modules and advanced capabilities are either currently in development or scheduled for upcoming releases.

### 5.1 The `Analyze` Module & Vision / OCR Pipeline (Partially Implemented / Work In Progress)
- **Current State:** The folder `Analyze/` exists in the repository root containing an empty `app.py`.
- **Intended Purpose:** In the root `requirements.txt`, advanced machine learning, computer vision, and OCR packages are already specified:
  - `torch`, `torchvision` (PyTorch Deep Learning framework)
  - `ultralytics` (YOLO object detection framework)
  - `easyocr`, `pytesseract` (Optical Character Recognition)
  - `opencv-python`, `scikit-image`, `pillow` (Image processing)
  - `fastapi`, `uvicorn` (High-performance microservice framework)
- **Pending Implementation:**
  - A standalone microservice designed to ingest screenshots of problem descriptions, whiteboard code, or handwritten algorithmic diagrams.
  - Automatic extraction of problem constraints and test cases from platforms that block DOM scrapers.
  - Optical bounding-box detection of algorithmic diagrams (e.g., recognizing tree structures or graph nodes drawn by students).

### 5.2 Multi-Platform Support (Currently LeetCode-Only)
- **Current State:** The Chrome extension content scripts and backend URL validators strictly target `https://leetcode.com/problems/*` and `https://leetcode.cn/*`.
- **Pending Implementation:**
  - Adapt the DOM parsing engine to support **Codeforces, HackerRank, GeeksForGeeks, AtCoder, and CodeChef**.
  - Abstract the DOM scraping logic into platform-specific adapter plugins.

### 5.3 Dynamic Code Execution Sandbox (vs. Current Static Heuristics)
- **Current State:** Time and space complexities are estimated via static heuristic inspection of code tokens, nested loops, and recursive calls.
- **Pending Implementation:**
  - Integration of an isolated containerized sandbox (e.g., Docker or WebAssembly / Pyodide) to execute the code against edge-case inputs.
  - Measuring empirical CPU cycles, peak memory allocation, and recursion depth to validate theoretical complexity against actual runtime profiles.

### 5.4 Real-Time In-Editor AI Copilot / Hint Engine
- **Current State:** The extension acts passively—it only analyzes code *after* an Accepted verdict is issued.
- **Pending Implementation:**
  - An interactive overlay widget inside the LeetCode Monaco editor that provides progressive hints (Socratic questioning) when a student fails multiple attempts without revealing the direct solution.
  - Detection of infinite loops or off-by-one errors before clicking Submit.

### 5.5 Social Learning, Cohorts & Benchmarking
- **Current State:** Each student operates in a private silo viewing only their personal metrics and goals.
- **Pending Implementation:**
  - University/Company Cohorts: Allowing instructors or campus placement cells to track cohort-wide mastery.
  - Anonymous peer benchmarking (e.g., "You solved Two Sum in fewer attempts than 78% of peers").

### 5.6 Spaced Repetition Revision Scheduler
- **Current State:** Solved problems are listed chronologically in the dashboard table.
- **Pending Implementation:**
  - An automated Spaced Repetition System (SRS) using the SM-2 algorithm.
  - Automatically alerting students via browser notifications when a problem they struggled on (e.g., $>3$ wrong attempts) is due for re-solving after 7, 14, or 30 days.

---

## 6. FEATURE STATUS MATRIX

| Component | Feature / Capability | Status | Description |
| :--- | :--- | :---: | :--- |
| **Extension** | Monaco Editor Code Extraction | **COMPLETE** | Injected script fetches full un-virtualized buffer via postMessage |
| **Extension** | Attempt Counter & Local Storage | **COMPLETE** | Tracks wrong/right/total per problem across browser restarts |
| **Extension** | Single-Use Dashboard Auth Token | **COMPLETE** | Passwordless handoff without exposing JWT in URL parameters |
| **Extension** | Multi-Platform (Codeforces, etc.) | *PLANNED* | Currently restricted to LeetCode domain |
| **Extension** | In-Editor Socratic Hints | *PLANNED* | Real-time assistance inside LeetCode page before submission |
| **Backend** | JWT Auth with Refresh Tokens | **COMPLETE** | Secure login, registration, token refresh, and bcrypt hashing |
| **Backend** | Dynamic Extension CORS & Headers | **COMPLETE** | Restricts API access to authorized Chrome extension IDs |
| **Backend** | Rate Limiting Engine | **COMPLETE** | Dual-bucket limits for IP and email brute-force prevention |
| **Backend** | Static DSA Pattern Detector | **COMPLETE** | Detects 20 core algorithmic patterns via syntax patterns |
| **Backend** | Heuristic Complexity Evaluator | **COMPLETE** | Predicts $O(1)$ to $O(2^n)$ time and auxiliary space |
| **Backend** | Multi-Score Evaluation Model | **COMPLETE** | 5-part weighted score (Correctness, Approach, Complexity, etc.) |
| **Backend** | EMA Topic Skill Scores | **COMPLETE** | Dynamic skill scores ($\alpha=0.4$) with statistical confidence |
| **Backend** | OpenRouter AI Report Generator | **COMPLETE** | Asynchronous synthesis with LLM or rule-based fallback |
| **Backend** | Day Streak Computation | **COMPLETE** | SQL date-partitioned consecutive active practice tracking |
| **Backend** | Isolated Code Execution Sandbox | *PLANNED* | Dynamic container execution for empirical profiling |
| **Dashboard** | Overview Hero Card & Metrics | **COMPLETE** | Real-time score ring, day streak, accuracy, and attempt stats |
| **Dashboard** | Topic Skill Map & Confidence | **COMPLETE** | Visual breakdown of mastery across data structure topics |
| **Dashboard** | AI Learning Report Viewer | **COMPLETE** | Formatted strengths, weaknesses, and weekly goals |
| **Dashboard** | Solution History Code Viewer | **COMPLETE** | Full code inspection for all historical accepted solutions |
| **Dashboard** | Study Goal Management | **COMPLETE** | Target date and daily minute tracking persisted to database |
| **Dashboard** | Spaced Repetition Notifications | *PLANNED* | Scheduled alerts to re-attempt difficult problems |
| **Analyze** | Computer Vision / OCR Pipeline | *IN PROGRESS* | Empty stub in repo; ML dependencies listed in requirements.txt |

---

## 7. API SPECIFICATION & ENDPOINTS

| HTTP Method | Route | Auth Required | Description |
| :--- | :--- | :---: | :--- |
| `GET` | `/api/health` | No | Database and service health check |
| `POST` | `/api/auth/register` | No | User registration with email, password, and optional name |
| `POST` | `/api/auth/login` | No | User authentication returning Access & Refresh tokens |
| `POST` | `/api/auth/refresh` | Refresh JWT | Issues new Access Token |
| `GET` | `/api/me` | Access JWT | Returns profile of authenticated user |
| `POST` | `/api/auth/dashboard-code` | Access JWT | Generates short-lived (2 min) single-use dashboard login code |
| `POST` | `/api/auth/exchange-dashboard-code` | No | Exchanges single-use code for JWT session |
| `POST` | `/api/submissions` | Access JWT | Records Accepted solution, triggers background evaluation & AI |
| `GET` | `/api/dashboard/summary` | Access JWT | Returns aggregate attempt statistics and problem list |
| `GET` | `/api/dashboard/full` | Access JWT | Rich dashboard data: stats, topic skills, streak, report status |
| `GET` | `/api/problems/<slug>` | Access JWT | Detailed attempt history and code snippets for a specific problem |
| `GET` | `/api/evaluations/<id>` | Access JWT | Static evaluation breakdown (complexity, patterns, scores) |
| `GET` | `/api/skills` | Access JWT | Per-topic skill scores and overall weighted DSA proficiency |
| `GET` | `/api/report` | Access JWT | Fetches latest AI report or returns pending generation status |
| `POST` | `/api/report/regenerate` | Access JWT | Forces re-evaluation of practice telemetry by AI coach |
| `GET` | `/api/goals` | Access JWT | Retrieves active study targets and daily minute quotas |
| `PUT` | `/api/goals` | Access JWT | Updates study targets, exam dates, and daily study minutes |

---

## 8. DATABASE SCHEMA DICTIONARY

```sql
-- Core User Entity
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(120),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- LeetCode Problem Catalog
CREATE TABLE problems (
    id SERIAL PRIMARY KEY,
    leetcode_id INTEGER,
    title VARCHAR(500) NOT NULL,
    slug VARCHAR(500) UNIQUE NOT NULL,
    url TEXT NOT NULL
);

-- Accepted Submissions & Telemetry
CREATE TABLE submissions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    problem_id INTEGER REFERENCES problems(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    language VARCHAR(80) NOT NULL,
    verdict VARCHAR(100) DEFAULT 'Accepted',
    right_attempts INTEGER DEFAULT 1,
    wrong_attempts INTEGER DEFAULT 0,
    total_attempts INTEGER DEFAULT 1,
    submitted_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Ephemeral Dashboard Authentication Handoff
CREATE TABLE dashboard_codes (
    id SERIAL PRIMARY KEY,
    code_hash VARCHAR(128) UNIQUE NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE
);

-- Topic Taxonomy Reference
CREATE TABLE topics (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) UNIQUE NOT NULL,
    parent_id INTEGER REFERENCES topics(id),
    slug VARCHAR(120) UNIQUE NOT NULL,
    description TEXT
);

-- Per-User Topic Skill Scores
CREATE TABLE skill_scores (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    score FLOAT DEFAULT 0.0,
    confidence FLOAT DEFAULT 0.0,
    problems_seen INTEGER DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_skill_user_topic UNIQUE (user_id, topic_id)
);

-- Submission Evaluation Results
CREATE TABLE evaluations (
    id SERIAL PRIMARY KEY,
    submission_id INTEGER UNIQUE REFERENCES submissions(id) ON DELETE CASCADE,
    correctness_score FLOAT,
    approach_score FLOAT,
    complexity_score FLOAT,
    optimization_score FLOAT,
    coverage_score FLOAT,
    overall_score FLOAT,
    time_complexity VARCHAR(50),
    space_complexity VARCHAR(50),
    detected_patterns TEXT,
    detected_topics TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    evaluated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- AI Learning Coach Snapshots
CREATE TABLE ai_reports (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    model_used VARCHAR(120),
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    submissions_hash VARCHAR(64),
    generated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Student Study Goals
CREATE TABLE user_goals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    goal_type VARCHAR(60) DEFAULT 'general',
    target_date DATE,
    daily_target_minutes INTEGER,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## 9. SECURITY, PERFORMANCE & ARCHITECTURAL DECISIONS

1. **Elimination of Credential Leakage in URLs:** Standard OAuth redirects frequently expose tokens in URL fragments (`#access_token=...`). LearnSense AI uses an atomic single-use ticket exchange mechanism (`dashboard_codes` table with `with_for_update()` database locks) that expires within 2 minutes and is wiped immediately upon first consumption.
2. **Mitigation of DOM Virtualization Truncation:** Modern code editors like Monaco only render lines currently within the browser viewport to optimize DOM memory. A standard content script reading `.view-line` elements would capture truncated code. LearnSense AI injects a bridge script into the page execution context to query `monaco.editor.getModels()[0].getValue()`, guaranteeing 100% complete solution captures.
3. **Optimized SQL Aggregation:** The endpoint `/api/dashboard/summary` utilizes SQL window functions (`ROW_NUMBER() OVER (PARTITION BY problem_id ORDER BY submitted_at DESC)`) with deferred loading on the heavy `code` column (`defer(Submission.code)`), reducing database wire transfer by over 90% during dashboard loads.
4. **Resilient AI Fallback:** Reliance on third-party LLMs presents uptime and latency challenges. The platform decouples report generation into asynchronous background worker threads and includes a rule-based deterministic fallback engine so the application remains 100% usable even during AI API outages.

---

## 10. HARDWARE, SOFTWARE & ENVIRONMENT REQUIREMENTS

### 10.1 Development & Server Stack
- **Operating System:** Cross-platform (Linux / Windows 10/11 / macOS)
- **Backend Runtime:** Python 3.10+ (Tested on Python 3.11 and Python 3.13)
- **Database:** PostgreSQL 14+ (Production) or SQLite 3.35+ (Local development)
- **Web Server:** Gunicorn WSGI Server (Production) / Werkzeug Development Server
- **Client Runtime:** Chromium-based browser supporting Manifest V3 (Google Chrome 109+, Brave, Edge)

### 10.2 Recommended Environment Variables (`.env`)
```env
APP_ENV=production
LOG_LEVEL=INFO
PORT=5000
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname
JWT_SECRET_KEY=at_least_32_characters_random_cryptographic_secret
DASHBOARD_ORIGIN=https://your-dashboard.onrender.com
DASHBOARD_URL=https://your-dashboard.onrender.com
EXTENSION_IDS=abcdefghijklmnopqrstuvwxyzabcdef
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxx
OPENROUTER_MODEL=google/gemma-3-27b-it:free
```

---

## 11. CONCLUSION & ACADEMIC SUMMARY

LearnSense AI successfully demonstrates how modern web browser extensions, asynchronous backend micro-architectures, heuristic static analysis, and generative AI can be unified into an interview preparation tool. By addressing the limitations of existing coding platforms—namely the loss of attempt history, lack of objective code complexity feedback, and absence of structured topic progression—LearnSense AI empowers students with actionable, data-driven mastery telemetry.

The modular design ensures that upcoming enhancements—such as the computer-vision-based `Analyze` module, dynamic sandbox execution, and spaced repetition schedulers—can seamlessly integrate into the existing ecosystem.
