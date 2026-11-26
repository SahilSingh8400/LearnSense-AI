# LearnSense AI 🚀

> **Automated LeetCode performance tracker, algorithmic complexity auditor, and AI learning companion.**

LearnSense AI tracks your LeetCode problem-solving practice in real time via a lightweight browser extension, evaluates time and space complexity with Google Gemini, and visualizes your progress on an interactive web dashboard with downloadable audit reports.

---

## ⚡ How It Works

1. **Solve on LeetCode** — The extension automatically detects your accepted submissions, language, and runtime without manual logging.
2. **AI Complexity Audit** — The backend analyzes your code against optimal time/space complexity ($O(1)$, $O(n)$, $O(n \log n)$, etc.) using Google Gemini.
3. **Track & Export** — Inspect topic mastery across DSA categories on the web dashboard and export interactive vector PDF reports.

---

## 🚀 Quick Start Guide

Follow these steps to get LearnSense AI running locally on your machine.

### 1. Prerequisites
- **Python 3.10+** installed
- **Google Chrome** (or Brave / Chromium-based browser)
- A free **[Google Gemini API Key](https://aistudio.google.com/app/apikey)**

### 2. Clone the Repository
```bash
git clone https://github.com/SahilSingh8400/LearnSense-AI.git
cd LearnSense-AI
```

### 3. Setup & Start Backend

Navigate into the `backend` directory:
```bash
cd backend
```

Create and activate a virtual environment:
```bash
python -m venv .venv

# Windows (PowerShell / CMD):
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Create your `.env` file from the example:
```bash
copy .env.example .env    # Windows
# cp .env.example .env    # macOS / Linux
```

Open `.env` (inside the `backend` folder) in your editor and add your **Gemini API Key**:
```env
GEMINI_API_KEY=AIzaSyYourGeminiAPIKeyHere
GEMINI_MODEL=gemini-1.5-flash
```

Now start the server (run this while inside the `backend` directory):
```bash
python app.py
```
> *Note: If your terminal is in the project root (`LearnSense-AI`), run `cd backend` first before running `python app.py`.*

> The API and web dashboard will be running at **`http://localhost:5000`**.

### 4. Load the Chrome Extension
1. Open Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked** and select the **`extension/`** folder from this repository.
4. Pin the **LearnSense AI** extension to your browser toolbar.

### 5. Start Practicing!
1. Click the extension icon in your browser toolbar (it will auto-connect to your local server).
2. Open any problem on [LeetCode](https://leetcode.com/problems/two-sum/) and submit an accepted solution.
3. Visit **`http://localhost:5000`** in your browser to view your analytics dashboard or download an interactive PDF report.

---

## ✨ Key Features

- **LeetCode Auto-Sync (Manifest V3)**: Captures accepted solutions, runtime, language, and attempt counts directly from LeetCode.
- **AI Complexity & Diagnostic Engine**: Evaluates Big-O time/space efficiency against optimal solutions and provides actionable practice roadmaps via Gemini.
- **Interactive Web Dashboard**: Real-time performance metrics, problem logs, topic skill proficiency breakdown, and goal tracking.
- **Interactive Vector PDF Reports**: Generates crisp, client-side PDF reports with clickable internal navigation, external problem links, and fillable revision checklists.
- **Seamless Local SSO**: Bi-directional session synchronization between the extension and dashboard with zero login friction.

---

## 📁 Repository Structure

```text
LearnSense-AI/
├── backend/                  # Flask REST API & AI diagnostic engine
│   ├── app.py                # Application server, routes & Gemini integration
│   ├── requirements.txt      # Python dependencies
│   └── .env.example          # Environment configuration template
├── dashboard/                # Static Web Dashboard UI
│   ├── index.html            # Main dashboard interface
│   ├── app.js                # Dashboard state & controller
│   ├── pdf-report.js         # Interactive PDF report generator
│   └── style.css             # Dashboard styling
└── extension/                # Manifest V3 Chrome Extension
    ├── manifest.json         # Extension configuration & permissions
    ├── content.js            # LeetCode submission listener
    ├── background.js         # Service worker & session management
    └── popup.html / popup.js # Extension popup interface
```

---

## 🧪 System Health Verification

To verify that the backend is up and running:
```bash
curl http://localhost:5000/api/health
```
Expected output:
```json
{"status": "ok", "app": "LearnSense-AI"}
```

---

## 🌐 Production Deployment

To deploy LearnSense AI to production (Render, Railway, Heroku, etc.), check out the step-by-step guide in [DEPLOYMENT.md](file:///c:/Users/Sahil/Desktop/LearnSense-AI/DEPLOYMENT.md).

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE.md](file:///c:/Users/Sahil/Desktop/LearnSense-AI/LICENSE.md) file for details.
