# 🚀 LearnSense AI — Complete Production Deployment & Distribution Guide

Welcome to the definitive deployment and distribution handbook for **LearnSense AI**! Whether you are deploying this for your own personal LeetCode grind or sharing it with classmates and the world, this guide will walk you through every step in plain English with visual aids and troubleshooting tips.

---

## 📑 Table of Contents
1. [Architecture & System Overview](#-architecture--system-overview)
2. [Section 1: Prerequisites & Accounts](#-section-1-prerequisites--accounts)
3. [Section 2: Deploy the Backend on Render](#-section-2-deploy-the-backend-on-render)
4. [Section 3: Deploy the Dashboard on Render](#-section-3-deploy-the-dashboard-on-render)
5. [Section 4: Configure the Extension for Production](#-section-4-configure-the-extension-for-production)
6. [Section 5: Install the Extension for Personal Use (Developer Mode)](#-section-5-install-the-extension-for-personal-use-developer-mode)
7. [Section 6: Distribute the Extension to Other Users](#-section-6-distribute-the-extension-to-other-users)
   - [Option A: Share as ZIP File (Free & Fast)](#option-a-share-as-zip-file-free-manual)
   - [Option B: Publish to Chrome Web Store (One-Click Install)](#option-b-publish-to-chrome-web-store-one-click-install)
8. [Section 7: How to Use the Extension](#-section-7-how-to-use-the-extension)
9. [Section 8: Troubleshooting & FAQs](#-section-8-troubleshooting--faqs)

---

## 🏗️ Architecture & System Overview

LearnSense AI consists of three interconnected components:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             BROWSER EXTENSION                               │
│                      (Chrome / Brave MV3 Manifest)                          │
│                                                                             │
│   • Captures all LeetCode submission attempts locally in chrome.storage     │
│   • Sends ONLY "Accepted" submissions to the Backend API                    │
│   • Requests single-use dashboard tokens for passwordless dashboard login   │
└───────────────────────┬─────────────────────────────────────────────────────┘
                        │
                        │ 1. HTTPS REST API (/api/*)
                        │    (JWT Bearer Auth + Extension Origin)
                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                BACKEND API                                  │
│                 (Flask + Gunicorn on Render Web Service)                    │
│                                                                             │
│   • Validates submissions & hashes temporary dashboard exchange codes       │
│   • Manages user accounts & JWT sessions                                    │
│   • Handles CORS for both Extension (`chrome-extension://`) and Dashboard   │
└───────────────────────┬─────────────────────────────────────────────────────┘
                        │
                        │ 2. PostgreSQL Connection (psycopg3)
                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            MANAGED DATABASE                                 │
│                       (Render PostgreSQL Database)                          │
│                                                                             │
│   • Stores users, problems, accepted solutions, and dashboard codes         │
└─────────────────────────────────────────────────────────────────────────────┘
                        ▲
                        │ 3. Fetches analytics via REST API
                        │    (CORS-protected via DASHBOARD_ORIGIN)
┌───────────────────────┴─────────────────────────────────────────────────────┘
│                              WEB DASHBOARD                                  │
│                     (Static HTML/CSS/JS on Render)                          │
│                                                                             │
│   • Pure static site (zero build step)                                      │
│   • Exchanges single-use auth code from URL for dashboard access token      │
│   • Displays problem breakdown, success rate, and historical code snippets  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 🔐 How the Authentication Flow Works
1. **User Sign Up / Login in Extension**: The user enters an email and password inside the extension popup. The backend validates credentials and issues a JWT stored safely in `chrome.storage.local`.
2. **Submitting Solutions**: When the user solves a LeetCode problem, the content script intercepts the submission result. If it's **Accepted**, the extension calls `POST /api/submissions` with the problem metadata, attempt counters, and source code.
3. **Opening the Dashboard**: When the user clicks **"View Dashboard"** in the popup:
   - The extension calls `POST /api/auth/dashboard-code` using its JWT.
   - The backend creates a cryptographic, single-use token (valid for only 2 minutes) and returns a URL: `https://your-dashboard.onrender.com/extension-login.html?code=<RAW_CODE>`.
   - The extension opens this link in a new browser tab.
   - The dashboard script reads the code parameter and calls `POST /api/auth/exchange-dashboard-code`.
   - The backend validates the code, marks it used, and grants an access token.
   - The user is logged in automatically without re-entering credentials!

---

## 🛠️ Section 1: Prerequisites & Accounts

Before starting, ensure you have:

1. **A GitHub Account**:
   - The LearnSense AI repository pushed to your personal GitHub account (either public or private).
   - Verify that your repo includes the [`backend/`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/backend), [`dashboard/`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/dashboard), and [`extension/`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/extension) folders.
2. **A Render Account**:
   - Sign up at [render.com](https://render.com) using your GitHub account (free tier works great!).
3. **A Chromium-based Browser**:
   - Google Chrome, Brave, Microsoft Edge, or Arc (with developer mode support).

---

## 🖥️ Section 2: Deploy the Backend on Render

The backend is a Python Flask API running on Gunicorn, backed by a managed PostgreSQL database.

### Step 2.1: Create the PostgreSQL Database
Render provides a managed PostgreSQL database that integrates directly with web services.

1. Log into your [Render Dashboard](https://dashboard.render.com/).
2. Click **New +** in the top navigation bar and select **PostgreSQL**.
3. Configure the database details:
   - **Name**: `learnsense-db`
   - **Database**: `learnsense` (or leave default)
   - **User**: `learnsense` (or leave default)
   - **Region**: Choose the region closest to you (e.g., *Oregon (US West)* or *Frankfurt (EU)*)
   - **PostgreSQL Version**: Leave default (e.g., 16)
   - **Instance Type**: **Free**
4. Click **Create Database**.
5. Wait 1–2 minutes until the status displays **Available**.
6. Scroll down to the **Connections** panel and locate the **Internal Database URL** (it looks like `postgres://learnsense:password@dpg-...-a/learnsense`).
   > [!IMPORTANT]
   > Keep this tab open or copy the **Internal Database URL** to your clipboard. You will paste this into the backend environment variables in Step 2.3.

---

### Step 2.2: Create the Web Service
Now, deploy the Python application inside [`backend/`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/backend).

1. In Render, click **New +** and select **Web Service**.
2. Select **Build and deploy from a Git repository** and connect your GitHub account.
3. Choose your `LearnSense-AI` repository.
4. Fill in the service configuration:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        RENDER WEB SERVICE SETTINGS                     │
├──────────────────────┬─────────────────────────────────────────────────┤
│ Setting              │ Value                                           │
├──────────────────────┼─────────────────────────────────────────────────┤
│ Name                 │ learnsense-api                                  │
│ Region               │ Same region as your database                    │
│ Branch               │ main (or master)                                │
│ Root Directory       │ backend                                         │
│ Runtime              │ Python 3                                        │
│ Build Command        │ pip install -r requirements.txt                 │
│ Start Command        │ gunicorn --bind 0.0.0.0:$PORT app:app           │
│ Instance Type        │ Free                                            │
└──────────────────────┴─────────────────────────────────────────────────┘
```

> [!NOTE]
> The application creates missing tables when Gunicorn starts. The build step
> must not import `app`, because production environment variables and the
> database are not guaranteed to be available during the build.

---

### Step 2.3: Configure Backend Environment Variables
Before deploying, scroll down to the **Environment Variables** section and add the following keys:

| Environment Variable | Value | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | *(Paste Internal Database URL from Step 2.1)* | Connection string to your Render PostgreSQL instance. |
| `JWT_SECRET_KEY` | Click **Generate** (or enter a random 32+ character string) | Secret key used to sign and verify JWT authentication tokens. |
| `FLASK_ENV` | `production` | Enables production security checks (e.g. strict CORS enforcement). |
| `DASHBOARD_ORIGIN` | `https://placeholder.onrender.com` *(temporary)* | Domain allowed to access backend via CORS. We update this in Section 3. |
| `DASHBOARD_URL` | `https://placeholder.onrender.com` *(temporary)* | Base URL used when redirecting the user to the web dashboard. |
| `JWT_ACCESS_MINUTES`| `1440` *(Optional, 1 day)* | Access-token lifetime; the extension refreshes it automatically using the refresh token. |

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Render Environment Variables Preview                                   │
├─────────────────────────┬──────────────────────────────────────────────┤
│ Key                     │ Value                                        │
├─────────────────────────┼──────────────────────────────────────────────┤
│ DATABASE_URL            │ postgresql://learnsense:...@dpg-...          │
│ JWT_SECRET_KEY          │ 8f9b2c3d4e5f6a1b2c3d4e5f6a7b8c9d0...         │
│ FLASK_ENV               │ production                                   │
│ DASHBOARD_ORIGIN        │ https://placeholder.onrender.com             │
│ DASHBOARD_URL           │ https://placeholder.onrender.com             │
└─────────────────────────┴──────────────────────────────────────────────┘
```

> [!TIP]
> Render automatically provides a **Generate** button next to secret fields. Click it for `JWT_SECRET_KEY` to instantly get a cryptographically secure value.

---

### Step 2.4: Deploy & Verify Backend Health
1. Click **Create Web Service**.
2. Render will trigger the first build. Monitor the deploy logs:
   - You should see `pip install` installing dependencies like `Flask`, `SQLAlchemy`, `psycopg`, and `gunicorn`.
   - You will see Gunicorn start and the database health check become available.
   - Finally: `==> Your service is live 🎉`.
3. Note your API URL at the top left of the page (e.g., `https://learnsense-api.onrender.com`).
4. **Test the health check**: Open a new browser tab and visit:
   ```text
   https://YOUR-BACKEND-APP.onrender.com/api/health
   ```
   You should see a successful JSON response:
   ```json
   {
     "database": "connected",
     "ok": true,
     "service": "LearnSense API"
   }
   ```
   If `"database": "connected"` appears, your backend and PostgreSQL database are fully operational!

---

## 📊 Section 3: Deploy the Dashboard on Render

The dashboard is located in [`dashboard/`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/dashboard). It consists of pure, lightweight HTML, CSS, and modern JavaScript with **zero build step** (no Webpack, Vite, or npm required).

### Step 3.1: Create the Static Site
1. In your [Render Dashboard](https://dashboard.render.com/), click **New +** and select **Static Site**.
2. Select your connected `LearnSense-AI` GitHub repository.
3. Configure the Static Site settings:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        RENDER STATIC SITE SETTINGS                     │
├──────────────────────┬─────────────────────────────────────────────────┤
│ Setting              │ Value                                           │
├──────────────────────┼─────────────────────────────────────────────────┤
│ Name                 │ learnsense-dashboard                            │
│ Branch               │ main (or master)                                │
│ Root Directory       │ *(leave blank)*                                 │
│ Build Command        │ echo 'No build step'                            │
│ Publish Directory    │ dashboard                                       │
└──────────────────────┴─────────────────────────────────────────────────┘
```

4. Click **Create Static Site**.
5. Render will deploy the static assets in under 30 seconds.
6. Once deployed, copy your dashboard URL from the top of the screen (e.g., `https://learnsense-dashboard.onrender.com`).
7. Verify both URLs before configuring the backend:
   - `https://YOUR-DASHBOARD-URL.onrender.com/`
   - `https://YOUR-DASHBOARD-URL.onrender.com/extension-login.html`

   Both must show LearnSense pages, not Render's `Not Found` page. If either
   URL returns `Not Found`, fix the static site's Publish Directory or use the
   actual deployed service URL before continuing.

---

### Step 3.2: Configure Dashboard API URL Auto-Detection
The dashboard needs to know where your backend API lives. You can either hardcode the backend URL or use auto-detection.

Open [`dashboard/config.js`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/dashboard/config.js). By default it contains:
```javascript
// Change this ONE value after deploying the Flask backend.
window.LEARNSENSE_API_BASE = 'http://localhost:5000/api';
```

Replace the contents of [`dashboard/config.js`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/dashboard/config.js) with this smart auto-detecting snippet:

```javascript
// LearnSense AI - Dashboard API Configuration
(function() {
  const isLocal = window.location.hostname === 'localhost' || 
                  window.location.hostname === '127.0.0.1';

  // Replace with your actual Render backend URL:
  const PROD_API = 'https://learnsense-api.onrender.com/api';

  window.LEARNSENSE_API_BASE = isLocal 
    ? 'http://localhost:5000/api' 
    : PROD_API;

  console.log('[LearnSense] API Base:', window.LEARNSENSE_API_BASE);
})();
```

> [!IMPORTANT]
> Replace `https://learnsense-api.onrender.com/api` with your actual Render API URL from Step 2.4. Commit and push this change to GitHub so Render automatically updates your static dashboard!

---

### Step 3.3: Link Dashboard to Backend (Update CORS & Redirect URL)
Now that you have your real dashboard URL (e.g., `https://learnsense-dashboard.onrender.com`):

1. Go back to your [Render Dashboard](https://dashboard.render.com/).
2. Click on your **learnsense-api** Web Service.
3. In the left sidebar, click **Environment**.
4. Update the two placeholder variables:
   - `DASHBOARD_ORIGIN` ➔ `https://learnsense-dashboard.onrender.com` *(Notice: no trailing slash!)*
   - `DASHBOARD_URL` ➔ `https://learnsense-dashboard.onrender.com` *(Notice: no trailing slash!)*
5. Click **Save Changes**.
6. Render will automatically redeploy the backend with the new CORS and redirect configuration.

---

## 🔌 Section 4: Configure the Extension for Production

The Chrome extension needs permission to communicate with your live Render backend instead of `localhost`.

### Step 4.1: Update Extension API Base URL
1. Open [`extension/config.js`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/extension/config.js) in your code editor.
2. Update `self.LEARNSENSE_API_BASE` to point to your live Render backend URL ending in `/api`:

```javascript
// extension/config.js

// Change this ONE value to your production Render URL:
self.LEARNSENSE_API_BASE = 'https://learnsense-api.onrender.com/api';
```

---

### Step 4.2: Update Manifest Host Permissions
Chrome MV3 requires extensions to explicitly declare all domains they communicate with.

1. Open [`extension/manifest.json`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/extension/manifest.json).
2. Locate the `"host_permissions"` array (lines 7–11):
   ```json
   "host_permissions": [
     "https://leetcode.com/*",
     "http://localhost:5000/*",
     "https://api.learnsense.ai/*"
   ],
   ```
3. Add your Render backend domain wildcard pattern. You can also safely remove localhost if you are packaging for end-users:
   ```json
   "host_permissions": [
     "https://leetcode.com/*",
     "https://learnsense-api.onrender.com/*"
   ],
   ```
4. Save the file.

---

## 💻 Section 5: Install the Extension (For Personal Use — Developer Mode)

This is the fastest, 100% free method to test and use your extension immediately on Chrome, Brave, or Edge.

### Step-by-Step Installation:
1. Open Google Chrome or Brave.
2. In the URL address bar, navigate to:
   ```text
   chrome://extensions/
   ```
   *(On Brave, navigate to `brave://extensions/`)*
3. In the top-right corner of the Extensions page, toggle the **Developer mode** switch to **ON**.
   ```text
   ┌────────────────────────────────────────────────────────┐
   │ Extensions                  [ Developer mode  (●) ON ] │
   ├────────────────────────────────────────────────────────┤
   │ [ Load unpacked ]  [ Pack extension ]  [ Update ]      │
   └────────────────────────────────────────────────────────┘
   ```
4. Click the **Load unpacked** button in the top-left menu.
5. In the file picker dialog, navigate to your repository and select the **`extension`** folder:
   ```text
   c:\Users\...\LearnSense-AI-Full-Implementation-v2\extension
   ```
6. Click **Select Folder**.
7. The **LearnSense AI** card will immediately appear in your extension list!
8. **Pin the extension**: Click the puzzle piece icon (🧩) on your browser toolbar and click the pin icon (📌) next to LearnSense AI.
9. Click the LearnSense AI icon in your toolbar:
   - Click **Sign Up**.
   - Enter your email and a password.
   - You're logged in!

---

## 👥 Section 6: Distribute the Extension to Other Users

You have two paths to share LearnSense AI with friends, study groups, or the public.

```
┌───────────────────────────────────────────────────────────────────────────┐
│                       CHOOSE YOUR DISTRIBUTION METHOD                     │
├─────────────────────────────────────┬─────────────────────────────────────┤
│ Option A: Share as ZIP File         │ Option B: Chrome Web Store          │
├─────────────────────────────────────┼─────────────────────────────────────┤
│ 🆓 Cost: 100% Free                  │ 💳 Cost: $5 one-time developer fee  │
│ ⚡ Setup: Instant (No review delay) │ ⏳ Review: 1–3 business days        │
│ 🛠️ Install: Manual (Developer Mode) │ 🌟 Install: 1-Click from Web Store  │
│ 🔄 Updates: Manual zip replacement  │ 🔄 Updates: Automatic background    │
│ 🎯 Best for: Friends, classmates    │ 🎯 Best for: Public launch, resume  │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

---

### Option A: Share as ZIP File (Free, Manual)

Ideal for sharing with classmates or friends without paying Google's developer registration fee.

#### 1. Prepare the ZIP Archive:
1. Ensure [`extension/config.js`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/extension/config.js) has your live Render API URL (`https://learnsense-api.onrender.com/api`).
2. Ensure [`extension/manifest.json`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/extension/manifest.json) includes `https://YOUR-APP.onrender.com/*` in `host_permissions`.
3. Open Windows Explorer, right-click the `extension` folder, and choose:
   **Send to ➔ Compressed (zipped) folder** (or use 7-Zip / WinRAR).
4. Name the file `LearnSense-AI-v2.0.0.zip`.

#### 2. Instructions to Give to Your Users:
Send your friends the ZIP file along with these 4 simple steps:
> **How to install LearnSense AI:**
> 1. Download and extract `LearnSense-AI-v2.0.0.zip` to your documents or desktop.
> 2. Open Chrome and go to `chrome://extensions/`.
> 3. Turn on **Developer mode** in the top-right corner.
> 4. Click **Load unpacked** (top-left) and select the unzipped `extension` folder.
> 5. Click the LearnSense AI icon in your browser toolbar to create an account!

---

### Option B: Publish to Chrome Web Store (One-Click Install)

Publishing to the Chrome Web Store gives you an official store listing, automatic updates for users, and a professional link to showcase on your portfolio or resume.

#### Step 1: Create a Google Developer Account
1. Visit the [Chrome Web Store Developer Console](https://chrome.google.com/webstore/devconsole).
2. Sign in with your Google account.
3. Pay the one-time **$5 USD** developer registration fee.

#### Step 2: Package the Extension ZIP
1. Verify the production configuration in [`extension/config.js`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/extension/config.js).
2. Remove any test comments or temporary code.
3. Select all files **inside** the `extension` folder:
   - `manifest.json`
   - `background.js`
   - `content.js`
   - `config.js`
   - `page-inject.js`
   - `popup.html`, `popup.css`, `popup.js`
   - `icons/` folder (`icon16.png`, `icon48.png`, `icon128.png`)
4. Compress these files directly into a ZIP archive.
   > [!WARNING]
   > Make sure `manifest.json` is at the **root** of the ZIP archive, not inside a nested subfolder!

#### Step 3: Upload and Fill Store Metadata
1. In the Chrome Developer Console, click **Add new item**.
2. Drag and drop your `.zip` archive.
3. Fill out the Store Listing tabs:
   - **Product Details**:
     - **Title**: LearnSense AI — LeetCode Analytics
     - **Summary**: Tracks LeetCode practice attempts and delivers detailed analytics on a hosted dashboard.
     - **Category**: *Productivity* or *Developer Tools*
   - **Graphic Assets**:
     - **Store Icon**: 128x128 PNG (use [`extension/icons/icon128.png`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/extension/icons/icon128.png))
     - **Screenshots**: At least one 1280x800 or 640x400 screenshot showing the popup stats and the hosted dashboard.
     - **Small Tile Promo**: 440x280 PNG.
   - **Privacy Practices**:
     - **Single Purpose**: "Track problem attempts and accepted solutions on LeetCode to provide personal learning analytics."
     - **Permission Justification for `storage`**: "Required to locally store the user's authentication token and count problem submission attempts."
     - **Host Permission `https://leetcode.com/*`**: "Required to detect problem submissions and outcomes on LeetCode problem pages."
     - **Host Permission `https://learnsense-api.onrender.com/*`**: "Required to sync accepted solutions and authenticate with the user's backend."
4. Click **Submit for Review**.
5. Google typically reviews extensions in **1 to 3 business days**. Once approved, anyone can install LearnSense AI with one click from your Chrome Web Store link!

---

## 🎯 Section 7: How to Use the Extension

Here is the everyday workflow for using LearnSense AI:

```text
  1. Open Extension Popup ────► Log In / Sign Up
           │
           ▼
  2. Visit LeetCode ──────────► Solve Problems Normally
           │
           ▼
  3. Attempting ──────────────► Wrong answers recorded LOCALLY in popup counter
           │
           ▼
  4. Accepted Solution! ──────► Full problem data + code synced to Render Backend
           │
           ▼
  5. Click "View Dashboard" ──► Passwordless redirect to your hosted analytics!
```

1. **Sign Up / Log In**: Click the extension icon in your browser toolbar, enter your email and password.
2. **Practice on LeetCode**: Open any problem on [leetcode.com/problems/](https://leetcode.com).
3. **Attempt Tracking**:
   - If you get *Wrong Answer*, *Time Limit Exceeded*, or *Runtime Error*, the extension increments your local attempt counter immediately.
   - The local popup displays real-time accuracy and attempt counts for each problem.
4. **Automatic Cloud Sync**:
   - As soon as your solution receives **Accepted**, the extension gathers your problem slug, title, language, attempts count, and accepted source code, then securely uploads it to your Render PostgreSQL database.
5. **View Your Dashboard**:
   - Click the extension icon and click **View Dashboard**.
   - A new tab opens with `extension-login.html?code=...`.
   - You are automatically authenticated and shown your total problems solved, accuracy percentage, and full submission history!

---

## 🩺 Section 8: Troubleshooting & FAQs

### 1. 502 Bad Gateway on Render Backend
- **Cause**: Gunicorn failed to bind to Render's assigned dynamic port.
- **Fix**: Check the **Start Command** in your Render Web Service settings. It MUST be:
  ```bash
  gunicorn --bind 0.0.0.0:$PORT app:app
  ```
  *(Do NOT use hardcoded port 5000 in your start command on Render)*.

---

### 2. Render Free Tier "Cold Starts" (30-second delay)
- **Symptom**: The first API request after some time takes 30–50 seconds to respond, or the extension popup shows a spinning loader.
- **Explanation**: Render's free tier automatically spins down web services after 15 minutes of inactivity. When a new request arrives, Render wakes the container up.
- **Solution**: 
  - Be patient on the very first request of the day! Once warm, it responds in milliseconds.
  - Optional: You can set up a free uptime monitor (like [UptimeRobot](https://uptimerobot.com) or [Cron-job.org](https://cron-job.org)) to ping `https://YOUR-APP.onrender.com/api/health` every 10 minutes to keep it awake.

---

### 3. Build Fails with Encoding or Dependency Errors
- **Symptom**: `UnicodeDecodeError` or package resolution failure during `pip install`.
- **Fix**:
  - Ensure [`backend/requirements.txt`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/backend/requirements.txt) is saved with **UTF-8** encoding without BOM.
  - Verify that the Python runtime in Render is set to **Python 3**.

---

### 4. Extension Cannot Connect to API ("Failed to fetch" / Network Error)
- **Symptom**: The popup shows "Unable to reach server" or network error in the extension console.
- **Checklist**:
  1. Did you include `/api` at the end of `LEARNSENSE_API_BASE` in [`extension/config.js`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/extension/config.js)?
     - ✅ Correct: `https://learnsense-api.onrender.com/api`
     - ❌ Incorrect: `https://learnsense-api.onrender.com`
  2. Did you add your backend domain to [`extension/manifest.json`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/extension/manifest.json)?
     - Ensure `"https://learnsense-api.onrender.com/*"` is in `"host_permissions"`.
  3. Did you reload the extension? Go to `chrome://extensions/` and click the **Reload icon (🔄)** on the LearnSense card.

---

### 5. CORS Errors in Browser Console
- **Symptom**: `Access to fetch at ... has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present`.
- **Fix**:
  - In your Render Web Service environment variables, verify that `DASHBOARD_ORIGIN` exactly matches your static site origin:
    ```text
    DASHBOARD_ORIGIN = https://learnsense-dashboard.onrender.com
    ```
  - **No trailing slash**: `https://learnsense-dashboard.onrender.com/` will cause CORS mismatches!
  - Note: Chrome extensions send requests with origin `chrome-extension://<id>`. The backend [`app.py`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/backend/app.py) handles extension origins automatically via regex in `handle_cors_for_extensions`.

---

### 6. Dashboard Shows "Signing you in..." Forever or "Missing sign-in code"
- **Symptom**: When clicking "View Dashboard", the tab loads `extension-login.html` but never redirects to `index.html`.
- **Fix**:
  1. Check `DASHBOARD_URL` in the backend environment variables. It must match the actual dashboard URL:
     ```text
     DASHBOARD_URL = https://learnsense-dashboard.onrender.com
     ```
  2. Dashboard codes expire after **2 minutes**. If a code was already used or expired, close the tab and click **View Dashboard** again in the popup to issue a fresh code.
  3. Ensure [`dashboard/config.js`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/dashboard/config.js) is pointing to your Render backend API URL and not `localhost`.

---

### 7. Non-Accepted Solutions Are Not Showing in the Database
- **Feature, not a bug!**
- The system is architected so the cloud database only stores **Accepted** solutions. All failed attempts (Wrong Answer, Runtime Error, etc.) are counted and preserved locally in your browser's extension storage, and their aggregate tally is uploaded along with the winning code once accepted!

---

## 🏁 Summary Checklist

Before sharing your project or showing it off, tick off this final checklist:

- [ ] Render PostgreSQL database created and status is `Available`.
- [ ] Backend Web Service deployed with `DATABASE_URL`, `JWT_SECRET_KEY`, and `FLASK_ENV=production`.
- [ ] Health check returns `{"ok": true, "database": "connected"}` at `/api/health`.
- [ ] Static Dashboard deployed on Render.
- [ ] Backend `DASHBOARD_ORIGIN` and `DASHBOARD_URL` updated with the dashboard URL.
- [ ] [`dashboard/config.js`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/dashboard/config.js) configured with the Render API URL.
- [ ] [`extension/config.js`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/extension/config.js) and [`extension/manifest.json`](file:///c:/Users/Sahil/Downloads/LearnSense-AI-Full-Implementation-v2/extension/manifest.json) updated for production.
- [ ] Extension loaded in Chrome Developer Mode and test login succeeded.
- [ ] LeetCode problem solved, and dashboard displays the accepted solution!

🎉 **Congratulations! LearnSense AI is fully deployed and ready to track your algorithmic journey!**
