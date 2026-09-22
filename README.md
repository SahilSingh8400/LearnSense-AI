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

Open `http://localhost:5000/dashboard`.

`dashboard/config.js` points to the local API by default.

### 3. Extension

1. Open Chrome/Brave extensions.
2. Enable Developer mode.
3. Load unpacked.
4. Select the `extension` folder.
5. Open LeetCode and solve a problem.

## Production deployment

1. Deploy `backend` as a Render Web Service.
2. Create a Render PostgreSQL database and set `DATABASE_URL`.
3. Set a strong random `JWT_SECRET_KEY`.
4. Deploy `dashboard` as a Render Static Site.
5. Put the dashboard URL into backend `DASHBOARD_URL`.
6. Put the dashboard origin into `DASHBOARD_ORIGIN`.
7. Change `extension/config.js` to the production API URL.
8. Add that API host to `manifest.json` and remove localhost before publishing.
9. Change `dashboard/config.js` to the production API URL.
10. Package the extension and publish/load the updated build.

## Important product behavior

The popup is intentionally lightweight. The hosted dashboard is where detailed reports belong.

The local popup keeps all attempts so it can show correct/wrong/accuracy immediately. The backend stores only successful solutions, with the complete attempt counters captured at the moment of success.
