# LearnSense API

Flask API for LearnSense AI.

## Stored remotely

Only `Accepted` submissions are accepted by `POST /api/submissions`.
Each accepted record contains the problem, code, language, timestamp and the
attempt counters calculated by the browser extension:

- `right_attempts`
- `wrong_attempts`
- `total_attempts`

The extension supports LeetCode, CodeChef, and HackerRank. The existing
submission schema remains platform-neutral; the problem URL identifies the
source website.

A non-Accepted request is rejected with HTTP 400.

## Main endpoints

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/me`
- `POST /api/auth/dashboard-code`
- `POST /api/auth/exchange-dashboard-code`
- `POST /api/submissions`
- `GET /api/dashboard/summary`
- `GET /api/problems/<slug>`

## Database

Development defaults to SQLite. Set `DATABASE_URL` to PostgreSQL for production.

The API creates missing tables on startup so a new Render PostgreSQL database
can boot without a manual migration command. Keep schema changes backwards
compatible and add a complete Flask-Migrate migration before changing the
models in a future release.
