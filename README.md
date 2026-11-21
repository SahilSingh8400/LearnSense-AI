# LearnSense AI 🚀

> **Intelligent, local-first LeetCode analytics, automated algorithmic performance auditing, and AI-powered learning diagnostics.**

LearnSense AI seamlessly tracks your LeetCode problem-solving practice locally, evaluates time and space complexity efficiency, generates comprehensive skill proficiency maps across DSA topics, and produces interactive, executive-ready PDF audit reports—all with zero friction and seamless single sign-on.

---

## 🌟 Key Features

### 1. ⚡ Frictionless Auto-Login & Dashboard SSO
- **Instant Popup Workspace**: Clicking the extension icon immediately opens your dashboard workspace, attempts, streak, and recent problem stats without tedious manual logins.
- **Persistent Local Caching**: Credentials and profiles are preserved in `chrome.storage.local`. Offline or temporary network latencies never log you out.
- **Bi-Directional SSO Bridge**: Signing into either the web dashboard or the extension automatically synchronizes your session across both surfaces.
- **Streamlined UI**: Removed confusing local reset triggers in favor of clean, persistent attempt histories and a dedicated "View Dashboard" launcher.

### 2. 🧩 Local-First LeetCode Tracker (Manifest V3)
- **Zero-Interruption Tracking**: Every attempt is recorded locally in real time so you can inspect question-by-question metrics immediately.
- **Smart Cloud Synchronization**: Only verified **Accepted** submissions (along with aggregated attempt counts, source code, language, and timestamps) are synced with the backend to keep server storage clean and efficient.

### 3. 🧠 Algorithmic Diagnostic & AI Coaching (Powered by Google Gemini)
- **Complexity & Optimality Detection**: Automatic classification of Big-O time and space bounds ($O(1)$, $O(\log n)$, $O(n)$, $O(n^2)$) comparing your solution against optimal approaches.
- **AI-Powered Synthesis**: Deep analysis powered by Google Gemini (or OpenRouter) generating personalized executive summaries, verified algorithmic strengths, targeted growth opportunities, and structured practice roadmaps.
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
         ├── AI Diagnostic Engine (Google Gemini / OpenRouter)
         └── SQLite (Dev) / PostgreSQL (Prod)
                           │
                           ▼
             Web Dashboard & Analytics UI
            ├── Real-time DSA Analytics (dashboard/index.html)
            ├── Complexity & Problem Breakdown
            └── Interactive Vector PDF Engine (dashboard/pdf-report.js)
```

---

## 🔑 Configuring Your Own Google Gemini API Key

LearnSense AI uses Google Gemini to evaluate your solutions, generate algorithmic performance summaries, analyze topic strengths/weaknesses, and suggest customized practice roadmaps. You can easily configure your own Gemini API key for free.

### Step 1: Get a Free Gemini API Key
1. Visit **[Google AI Studio](https://aistudio.google.com/app/apikey)**.
2. Sign in with your Google account.
3. Click **"Create API key"** (or **"Get API key"**).
4. Copy the generated API key (it typically begins with `AIzaSy...`).

### Step 2: Add the API Key to Your Environment
In the `backend/` directory (or root), create or open your `.env` file (copied from `.env.example`):

```bash
# In backend/.env:
GEMINI_API_KEY=AIzaSyYourGeminiAPIKeyHere
GEMINI_MODEL=gemini-1.5-flash
```

### Supported Gemini Models
You can configure `GEMINI_MODEL` to any of the following supported models (defaults to `gemini-1.5-flash`):
- `gemini-1.5-flash` *(Recommended: extremely fast, high free-tier rate limits)*
- `gemini-2.0-flash` *(Next-generation low-latency model)*
- `gemini-1.5-pro` *(Complex algorithmic reasoning & detailed feedback)*
- `gemini-1.5-flash-8b` *(Ultra-lightweight model)*

> **Alternative (OpenRouter)**: If you prefer using OpenRouter, set `OPENROUTER_API_KEY=sk-or-v1-...` and `OPENROUTER_MODEL=liquid/lfm-3-1.7b:free` instead. If both are provided, LearnSense prioritizes Google Gemini.

---

## 📁 Repository Structure

```text
LearnSense-AI/
├── backend/                  # Flask REST API backend
│   ├── instance/             # Local SQLite database (auto-generated)
│   ├── migrations/           # Database migration versions
│   ├── .env.example          # Environment configuration template
│   ├── app.py                # Main Flask API, AI synthesis & models
│   └── requirements.txt      # Clean backend dependencies
├── dashboard/                # Static Web Dashboard
│   ├── icons/                # Brand emblems & favicons
│   ├── app.js                # Dashboard controller & tab navigation
│   ├── config.js             # API base URL configuration
│   ├── extension-login.html  # SSO handoff & authentication page
│   ├── index.html            # Main analytics dashboard UI
│   ├── pdf-report.js         # Interactive Vector PDF generator
│   └── style.css             # Executive Obsidian & Indigo stylesheet
├── extension/                # Chrome/Brave Manifest V3 Extension
│   ├── icons/                # Extension action icons (16, 48, 128)
│   ├── background.js         # Service worker, auto-login & sync
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
├── .env.example              # Root environment template
├── .gitignore                # Clean git ignore configuration
├── requirements.txt          # Root Python dependencies
└── README.md                 # Complete documentation
```

---

## 🚀 Quick Start Guide (Use as Your Own)

Follow these simple steps to set up LearnSense AI on your local machine:

### 1. Prerequisites
- **Python 3.10+** installed
- **Google Chrome** or **Brave Browser**
- A free **[Gemini API Key](https://aistudio.google.com/app/apikey)**

### 2. Clone the Repository
```bash
git clone https://github.com/SahilSingh8400/LearnSense-AI.git
cd LearnSense-AI
```

### 3. Backend Setup
```bash
# Navigate to backend
cd backend

# Create a virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows (PowerShell / Command Prompt):
.venv\Scripts\activate
# On macOS / Linux:
source .venv/bin/activate

# Install required dependencies
pip install -r requirements.txt

# Create your .env file from the template
copy .env.example .env    # On Windows
# cp .env.example .env    # On macOS / Linux
```

Open `backend/.env` in any text editor and paste your **Gemini API key**:
```env
GEMINI_API_KEY=AIzaSyYourRealKeyHere
GEMINI_MODEL=gemini-1.5-flash
```

Now start the server:
```bash
python app.py
```
*The API will start at `http://localhost:5000` with automated table initialization and local SQLite storage.*

### 4. Open the Web Dashboard
Open your browser and navigate to:
```text
http://localhost:5000/
```
*(Or `http://localhost:5000/dashboard/`)*. The dashboard will load with full analytics, topic skill proficiency maps, and the **"Download Report (PDF)"** button.

### 5. Install the Chrome/Brave Extension
1. Open Chrome and go to `chrome://extensions/`.
2. Turn on **Developer mode** (toggle in the upper right corner).
3. Click **Load unpacked**.
4. Browse to and select the `extension/` folder inside the `LearnSense-AI` repository.
5. Click the **LearnSense AI** icon pinned in your browser toolbar!
   - It will automatically connect and log you in.
   - Now open any problem on [LeetCode](https://leetcode.com/problems/two-sum/) and start coding! Every attempt is recorded locally, and upon **Accepted**, your solution, complexity, and attempt counters are synchronized automatically.

---

## 📊 Generating the Interactive PDF Report

1. Open the Web Dashboard at `http://localhost:5000/`.
2. Click **"Download Report (PDF)"** (available in the header, hero section, and AI Report tab).
3. Open the downloaded PDF in any viewer (Adobe Acrobat, Chrome, Microsoft Edge, or Preview):
   - **Clickable Navigation**: Click any pill in the top `QUICK NAV:` bar (`01 AI Diagnostic`, `02 Skill Map`, `03 Problem Log`, `04 Goals`, `05 Action Notes`) to jump directly to that section.
   - **Clickable Stat Cards**: Click any of the 4 hero stat cards to jump to relevant breakdown sections.
   - **Outlines / Bookmarks Sidebar**: Use the native PDF bookmarks panel to navigate between sections.
   - **LeetCode Links**: Click any problem title to open its exact page on LeetCode.
   - **Interactive Form Fields**: Check off steps in the *Suggested Learning Path* or type personal notes directly into the *Action Plan & Revision Commitments* text box.

---

## 🧪 Automated Testing & Verification

Run the test suite to verify that the backend, authentication, database, auto-login, LeetCode submission ingestion, and AI diagnostics are working correctly:

```bash
# 1. Verify complete backend, static dashboard routing, and AI diagnostics
python tests/verify_all.py

# 2. Verify extension auto-login, submission sync, and dashboard handoff
python tests/test_extension_workflow.py
```

---

## 🔌 API Endpoints Reference

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/health` | `GET` | Health check and system uptime |
| `/api/auth/auto-login` | `GET`, `POST` | Frictionless auto-login & SSO for extension and dashboard |
| `/api/auth/login` | `POST` | User sign-in with email & password |
| `/api/auth/register` | `POST` | New user account registration |
| `/api/auth/refresh` | `POST` | Exchange refresh token for fresh JWT access token |
| `/api/me` | `GET` | Current authenticated user profile |
| `/api/auth/dashboard-code` | `POST` | Generate secure one-time SSO dashboard handoff code |
| `/api/auth/exchange-dashboard-code` | `POST` | Exchange handoff code for dashboard access token |
| `/api/submissions` | `POST` | Ingest accepted LeetCode submission and evaluate complexity |
| `/api/dashboard/full` | `GET` | Complete metrics, problem list, and evaluated topics |
| `/api/report` | `GET` | Retrieve AI algorithmic performance synthesis |
| `/api/report/regenerate` | `POST` | Trigger fresh Gemini AI analysis & synthesis |
| `/api/skills` | `GET` | DSA topic skill scores and AI confidence ratings |
| `/api/goals` | `GET`, `POST` | Get or update user learning goals & daily targets |

---

## 🌐 Production Deployment

Ready to host LearnSense AI for your university, team, or portfolio?

1. **Deploy Backend to Render / Railway / Heroku**:
   - Set environment variables: `FLASK_ENV=production`, `DATABASE_URL=postgresql://...`, `JWT_SECRET_KEY=long-random-string`, `GEMINI_API_KEY=your-gemini-key`.
   - Start command: `gunicorn --bind 0.0.0.0:$PORT app:app`.
   - See [DEPLOYMENT.md](./DEPLOYMENT.md) for full deployment instructions.
2. **Update URLs for Hosted Mode**:
   - Update `extension/config.js` with your production API URL (e.g. `https://learnsense-api.onrender.com/api`).
   - Update `dashboard/config.js` with your production API URL.
   - Update `extension/manifest.json` host permissions to match your production API domain.

---

## 📄 License

This project is licensed under the MIT License - see the `LICENSE` file for details.
