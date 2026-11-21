# LearnSense AI 🚀

> **Intelligent, local-first LeetCode analytics, automated algorithmic performance auditing, and AI-powered learning diagnostics.**

LearnSense AI seamlessly tracks your LeetCode problem-solving practice locally, evaluates time and space complexity efficiency, generates comprehensive skill proficiency maps across DSA topics, and produces interactive, executive-ready PDF audit reports—all with zero friction and seamless single sign-on.

---

## 🌟 Key Features

### 1. ⚡ Frictionless Auto-Login & Dashboard SSO
- **Instant Popup View**: Clicking the extension icon immediately opens your dashboard workspace, attempts, streak, and recent problem stats without tedious manual logins.
- **Persistent Local Caching**: Credentials and profiles are preserved in `chrome.storage.local`. Offline or temporary network latencies never log you out.
- **Bi-Directional SSO Bridge**: Signing into either the web dashboard or the extension automatically synchronizes your session across both surfaces.
- **Streamlined UI**: Removed confusing local reset triggers in favor of clean, persistent attempt histories and a dedicated "View Dashboard" launcher.

### 2. 🧩 Local-First LeetCode Tracker (Manifest V3)
- **Zero-Interruption Tracking**: Every attempt is recorded locally in real time so you can inspect question-by-question metrics immediately.
- **Smart Cloud Synchronization**: Only verified **Accepted** submissions (along with aggregated attempt counts, source code, language, and timestamps) are synced with the backend to keep server storage clean and efficient.

### 3. 🧠 Algorithmic Diagnostic & AI Coaching
- **Complexity & Optimality Detection**: Automatic classification of Big-O time and space bounds ($O(1)$, $O(\log n)$, $O(n)$, $O(n^2)$) comparing your solution against optimal approaches.
- **AI-Powered Synthesis**: Deep analysis powered by Google Gemini / OpenRouter generating personalized executive summaries, verified algorithmic strengths, targeted growth opportunities, and structured practice roadmaps.
- **Topic Skill Proficiency Map**: Topic-by-topic mastery scoring (Arrays, Binary Search, Dynamic Programming, Graphs, etc.) with AI confidence metrics.

### 4. 📄 Interactive Vector PDF Report Generator
- **100% Client-Side & Zero Dependencies**: Generates crisp, standard PDF 1.4 documents directly in your browser without external rendering services or canvas rasterization.
- **Clickable Internal Navigation**: Quick-jump navigation bar and interactive hero stat cards that instantly jump to report sections via PDF `/GoTo` destinations.
- **Native Document Outlines / Bookmarks**: Includes structured PDF bookmarks that automatically display in the sidebar of Adobe Acrobat, Chrome, Edge, and Apple Preview.
- **External Links & Mailto**: Click problem titles to open them directly on LeetCode; click learner emails to open mail clients.
- **Fillable Interactive AcroForm**:
  - Interactive checkboxes on suggested roadmap steps that you can toggle directly inside the PDF.
  - Fillable multi-line text area for personal notes, revision goals, or mentor feedback.

---

## 🏗️ System Architecture

```text
       LeetCode Problem Page (leetcode.com/problems/*)
                           │
                 [content.js + page-inject.js]
                           │
                           ▼
              Chrome Extension (Manifest V3)
             ├── Persistent Local Storage (chrome.storage.local)
             ├── Instant Popup Workspace (popup.html + popup.js)
             └── Dashboard SSO Bridge (content-dashboard.js)
                           │
            (On Accepted Submission / SSO Auth)
                           │
                           ▼
          Flask REST API (Python 3.10+ / Gunicorn)
         ├── JWT Auth & Auto-Login (/api/auth/*)
         ├── Complexity & Submission Ingestion (/api/submissions)
         ├── AI Diagnostic Engine (Gemini / OpenRouter)
         └── SQLite (Dev) / PostgreSQL (Prod)
                           │
                           ▼
             Web Dashboard & Analytics UI
            ├── Real-time DSA Analytics (dashboard/index.html)
            ├── Complexity & Problem Breakdown
            └── Interactive Vector PDF Engine (dashboard/pdf-report.js)
```

---

## 📁 Repository Structure

```text
LearnSense-AI/
├── backend/                  # Flask REST API backend
│   ├── instance/             # Local database instance (git-ignored)
│   ├── migrations/           # Database migration versions
│   ├── .env.example          # Example environment configuration
│   ├── app.py                # Main Flask application & routes
│   └── requirements.txt      # Python dependencies
├── dashboard/                # Static Web Dashboard
│   ├── icons/                # Brand emblems & favicons
│   ├── app.js                # Dashboard controller & tab logic
│   ├── config.js             # API base URL configuration
│   ├── extension-login.html  # SSO handoff & authentication page
│   ├── index.html            # Main analytics dashboard UI
│   ├── pdf-report.js         # Interactive Vector PDF generator
│   └── style.css             # Executive Obsidian & Indigo stylesheet
├── extension/                # Chrome/Brave Manifest V3 Extension
│   ├── icons/                # Extension action icons (16, 48, 128)
│   ├── background.js         # Background service worker & auto-login
│   ├── config.js             # API URL configuration
│   ├── content.js            # LeetCode attempt scraper & observer
│   ├── content-dashboard.js  # Dashboard SSO sync bridge
│   ├── manifest.json         # Extension Manifest V3 definition
│   ├── page-inject.js        # Monaco/CodeMirror code extraction bridge
│   ├── popup.css             # Popup UI styling
│   ├── popup.html            # Extension popup layout
│   └── popup.js              # Instant workspace & session controller
├── tests/                    # Integration & verification test suites
│   ├── test_extension_workflow.py # End-to-end extension & API tests
│   └── verify_all.py         # Full backend & AI diagnostic tests
├── .gitignore                # Production git ignore configuration
├── requirements.txt          # Root Python dependencies
└── README.md                 # Project documentation
```

---

## 🚀 Quick Start & Local Setup

### 1. Prerequisites
- Python 3.10+
- Google Chrome or Brave Browser

### 2. Backend Setup
```bash
# Navigate to the backend directory
cd backend

# Create and activate virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure your environment
copy .env.example .env   # On Windows
# cp .env.example .env   # On macOS/Linux

# Start the Flask API server
python app.py
```
The backend starts at `http://localhost:5000`. SQLite is used automatically when `DATABASE_URL` is omitted.

### 3. Web Dashboard
The dashboard is served directly by the backend at:
- `http://localhost:5000/` or `http://localhost:5000/dashboard/`

*(Alternatively, you can serve `dashboard/` with any static web server like `python -m http.server 3000`).*

### 4. Chrome Extension Installation
1. Open Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked**.
4. Select the `extension/` directory from this repository.
5. Click the LearnSense AI icon in your browser toolbar—it automatically connects and displays your session!

---

## 🧪 Running Automated Tests

Run the comprehensive integration test suite to verify the complete backend, authentication, LeetCode ingestion, and AI diagnostics:

```bash
# Verify end-to-end API & AI diagnostic functionality
python tests/verify_all.py

# Verify Chrome Extension auto-login, submission sync, and dashboard handoff
python tests/test_extension_workflow.py
```

---

## 🔌 API Endpoints Reference

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/health` | `GET` | Health check and system uptime |
| `/api/auth/auto-login` | `GET`, `POST` | Frictionless auto-login & SSO for extension/dashboard |
| `/api/auth/login` | `POST` | Email and password authentication |
| `/api/auth/register` | `POST` | New learner account registration |
| `/api/auth/refresh` | `POST` | Exchange refresh token for new access token |
| `/api/me` | `GET` | Authenticated user profile and metadata |
| `/api/auth/dashboard-code` | `POST` | Generate secure one-time SSO handoff code |
| `/api/auth/exchange-dashboard-code` | `POST` | Exchange handoff code for dashboard session |
| `/api/submissions` | `POST` | Ingest accepted LeetCode submission |
| `/api/dashboard/full` | `GET` | Complete learner metrics, topics, and problem logs |
| `/api/report` | `GET` | AI algorithmic performance diagnostic and advice |
| `/api/report/regenerate` | `POST` | Request freshly synthesized AI diagnostic |
| `/api/skills` | `GET` | Topic skill proficiency map and confidence metrics |
| `/api/goals` | `GET`, `POST` | View or update targeted learning commitments |

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
