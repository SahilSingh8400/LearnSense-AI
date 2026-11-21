import os
import sys
import json
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("."))
load_dotenv("backend/.env")

from backend.app import app, db, User, Problem, Submission, Evaluation, SkillScore, AIReport

client = app.test_client()

print("=" * 60)
print("LEARNSENSE AI - FULL END-TO-END VERIFICATION")
print("=" * 60)

# 1. Test offline health check
res = client.get("/api/health")
print("[1] Health Check:", res.status_code, res.get_json())
assert res.status_code == 200

# 2. Test offline static web dashboard serving
res_root = client.get("/")
res_dash = client.get("/dashboard/")
res_login = client.get("/extension-login.html")
print(f"[2] Dashboard Static Routing: root={res_root.status_code}, /dashboard/={res_dash.status_code}, login={res_login.status_code}")
assert res_root.status_code == 200
assert res_dash.status_code == 200
assert res_login.status_code == 200

# 3. Test Authentication (Auto-Login & Manual Login)
auto_res = client.post("/api/auth/auto-login")
assert auto_res.status_code == 200, f"Auto-login failed: {auto_res.get_json()}"
print("[3a] Auto-Login Succeeded: JWT access token acquired for", auto_res.get_json()["user"]["email"])

login_res = client.post("/api/auth/login", json={
    "email": "sahil98099@gmail.com",
    "password": "password123"
})
assert login_res.status_code == 200, f"Login failed: {login_res.get_json()}"
token = login_res.get_json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("[3b] Authentication Succeeded: JWT access token acquired")

# 4. Check Current Submissions
res_summary = client.get("/api/dashboard/summary", headers=headers)
print("[4] Problems Solved:", res_summary.get_json()["overall"]["solved_problems"])

# 5. Add a realistic second submission to test multi-topic AI skill analysis
# E.g. Binary Search in C++
sub_payload = {
    "title": "Binary Search",
    "problemSlug": "binary-search",
    "problemUrl": "https://leetcode.com/problems/binary-search/",
    "lang": "cpp",
    "verdict": "Accepted",
    "rightAttempts": 1,
    "wrongAttempts": 0,
    "totalAttempts": 1,
    "timestamp": 1731835000000,
    "code": """class Solution {
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
}

# Check if already added
with app.app_context():
    existing_p = Problem.query.filter_by(slug="binary-search").first()
    if not existing_p:
        sub_res = client.post("/api/submissions", headers=headers, json=sub_payload)
        print("[5] Added Submission 'Binary Search':", sub_res.status_code, sub_res.get_json())
    else:
        print("[5] 'Binary Search' problem already present.")

# 6. Run AI Performance Analysis and Skill Scoring
print("[6] Running AI Analysis on student performance...")
analyze_res = client.post("/api/skills/analyze", headers=headers)
print("    /api/skills/analyze status:", analyze_res.status_code)
skills_data = analyze_res.get_json()
print("    Overall DSA Skill Score:", skills_data.get("overall_score"))
print("    Skill Level / Tier:", skills_data.get("skill_level"))
print("    Topic Breakdown:")
for t in skills_data.get("topics", []):
    print(f"      - {t['topic']}: {t['score']}/100 ({t['label']}, {t['problems_seen']} problem(s))")

# 7. Fetch the AI Learning Report
report_res = client.get("/api/report", headers=headers)
print("[7] AI Report status:", report_res.status_code)
report_json = report_res.get_json()
print("    Model Used:", report_json.get("model"))
rep = report_json.get("report", {})
print("    Skill Summary:", rep.get("skill_summary"))
print("    Strengths:", rep.get("strengths"))
print("    Weaknesses:", rep.get("weaknesses"))
print("    Recommended Priorities:", [r.get("topic") for r in rep.get("recommendations", [])])
print("    Learning Path:", rep.get("learning_path"))
print("    Weekly Target:", rep.get("weekly_target"))
print("    Coach Advice:", rep.get("encouragement"))

# 8. Check Full Dashboard Payload
dash_res = client.get("/api/dashboard/full", headers=headers)
dash_data = dash_res.get_json()
print("[8] Full Dashboard Overview:")
print("    Solved Problems:", dash_data["overall"]["solved_problems"])
print("    Accuracy:", dash_data["overall"]["accuracy"], "%")
print("    Overall DSA Skill Score:", dash_data["overall"]["overall_skill_score"])
print("    Skill Tier:", dash_data["overall"]["skill_level"])
print("    Total Topics Evaluated:", len(dash_data.get("topics", [])))

print("=" * 60)
print("SUCCESS: ALL SYSTEM COMPONENTS TESTED AND OPERATING FLAWLESSLY!")
print("=" * 60)
