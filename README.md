# LearnSense AI — Full Implementation

LearnSense AI is a Chrome/Brave MV3 extension + Flask/PostgreSQL API + hosted dashboard.

## Final data flow

```text
LeetCode
   |
   v
Browser extension
   |
   +--> EVERY attempt -> Chrome local storage (popup stats/history)
   |
   +--> ONLY Accepted -> Backend API
                          |
                          v
                      PostgreSQL
                          |
                          v
                   Hosted Dashboard
```

### Backend rule
The API **rejects non-Accepted submissions**. On Accepted, the extension sends:

- problem name
- problem slug and URL
- right attempts
- wrong attempts
- total attempts
- accepted code
- language
- timestamp

The attempt counters are maintained locally per problem so they do not become inaccurate when the recent history is capped.

## Authentication

- First use: Sign up or Login in the extension.
- The access token is stored in `chrome.storage.local`, which survives browser restarts.
- `View Dashboard` does not put the JWT in the URL. The extension requests a short-lived, one-use dashboard code and opens the hosted dashboard with that code.
- The dashboard exchanges the one-use code for its own access token and remembers it in browser local storage.

For a production release, replace the simple long-lived access token with a refresh-token/session system and HTTPS-only deployment.

## Local development

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

The API starts at `http://localhost:5000`.
SQLite is used automatically if `DATABASE_URL` is not set.

### 2. Dashboard

The dashboard is static. From the `dashboard` directory run any static server, for example:

```bash
python -m http.server 3000
```

Open `http://localhost:3000`. The Flask-served `http://localhost:5000/dashboard`
route is also available when the backend is running, but the static server
matches the production layout.

`dashboard/config.js` points to the local API by default.

### 3. Extension

1. Open Chrome/Brave extensions.
2. Enable Developer mode.
3. Load unpacked.
4. Select the `extension` folder.
5. Open LeetCode, CodeChef, or HackerRank and solve a problem.

### Supported coding websites

The extension tracks attempts on:

- LeetCode (`leetcode.com`)
- CodeChef (`codechef.com`)
- HackerRank (`hackerrank.com`)

Click the site's submit button. Every recognized result is stored locally in
the popup. Accepted submissions include the problem URL, platform-specific
problem slug, language, editor contents, and attempt counters when they are
synced to the backend. The extension recognizes each site's common accepted,
wrong-answer, time-limit, memory-limit, runtime, compile, and internal-error
result labels.

## Production deployment

Follow [DEPLOYMENT.md](./DEPLOYMENT.md) in order. The important values are:

| Component | Value to configure |
| --- | --- |
| Backend `DASHBOARD_URL` | Full dashboard origin, with no trailing slash |
| Backend `DASHBOARD_ORIGIN` | Same dashboard origin, with no path |
| `dashboard/config.js` | Backend URL ending in `/api` |
| `extension/config.js` | Same backend URL ending in `/api` |
| `extension/manifest.json` | Exact backend host in `host_permissions` |

Do not publish the extension until the backend health check and dashboard
sign-in flow both work over HTTPS.

## Important product behavior

The popup is intentionally lightweight. The hosted dashboard is where detailed reports belong.

The local popup keeps all attempts so it can show correct/wrong/accuracy immediately. The backend stores only successful solutions, with the complete attempt counters captured at the moment of success.
