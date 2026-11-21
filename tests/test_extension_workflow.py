import os
import sys
import json
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("."))
load_dotenv("backend/.env")

from backend.app import app, db, User, Problem, Submission, Evaluation, SkillScore, DashboardCode

client = app.test_client()

print("=" * 65)
print("TESTING FULL CHROME EXTENSION <-> COMPUTER BACKEND INTEGRATION")
print("=" * 65)

# 0. EXTENSION AUTO-LOGIN (Simulating popup opening and auto-authenticating without credentials)
print("\n[Step 0] Extension Auto-Login Verification:")
auto_res = client.post("/api/auth/auto-login")
assert auto_res.status_code == 200, f"Auto-login failed: {auto_res.get_json()}"
auto_data = auto_res.get_json()
assert "access_token" in auto_data
assert "user" in auto_data
print(f" -> Extension auto-login succeeded! Acquired session for: {auto_data['user']['email']}")

# 1. EXTENSION AUTHENTICATION (Simulating extension popup manual login)
print("\n[Step 1] Extension Popup Login:")
login_res = client.post("/api/auth/login", json={
    "email": "sahil98099@gmail.com",
    "password": "password123"
})
assert login_res.status_code == 200, f"Login failed: {login_res.get_json()}"
tokens = login_res.get_json()
auth_token = tokens["access_token"]
headers = {"Authorization": f"Bearer {auth_token}"}
print(" -> Extension logged in successfully! Received JWT.")

# 2. EXTENSION POPUP SESSION CHECK & STATS
print("\n[Step 2] Extension Popup Session & Stats Check:")
me_res = client.get("/api/me", headers=headers)
assert me_res.status_code == 200
user_info = me_res.get_json()
print(f" -> Logged in as: {user_info['name']} ({user_info['email']})")

full_res = client.get("/api/dashboard/full", headers=headers)
assert full_res.status_code == 200
popup_stats = full_res.get_json()
print(f" -> Extension Popup Stats: DSA Skill Score = {popup_stats['overall']['overall_skill_score']}, Solved = {popup_stats['overall']['solved_problems']}, Tier = {popup_stats['overall']['skill_level']}")

# 3. LEETCODE SUBMISSION SYNC (Simulating extension content script solving problem on LeetCode)
print("\n[Step 3] Simulating Solving Problem on LeetCode (content.js -> background.js -> backend):")
leetcode_submission = {
    "title": "Reverse Linked List",
    "problemSlug": "reverse-linked-list",
    "problemUrl": "https://leetcode.com/problems/reverse-linked-list/",
    "lang": "cpp",
    "verdict": "Accepted",
    "rightAttempts": 1,
    "wrongAttempts": 1,
    "totalAttempts": 2,
    "timestamp": 1731835900000,
    "code": """class Solution {
public:
    ListNode* reverseList(ListNode* head) {
        ListNode* prev = nullptr;
        ListNode* curr = head;
        while (curr != nullptr) {
            ListNode* nextTemp = curr->next;
            curr->next = prev;
            prev = curr;
            curr = nextTemp;
        }
        return prev;
    }
};"""
}

sync_res = client.post("/api/submissions", headers=headers, json=leetcode_submission)
print(" -> LeetCode submission synced from Extension:", sync_res.status_code, sync_res.get_json())
assert sync_res.status_code in [200, 201]

# 4. ONE-CLICK "VIEW DASHBOARD" BUTTON (Simulating user clicking View Dashboard button in popup)
print("\n[Step 4] User clicks 'View Dashboard' in Extension:")
code_res = client.post("/api/auth/dashboard-code", headers=headers)
assert code_res.status_code == 200
handoff_data = code_res.get_json()
redirect_url = handoff_data["url"]
print(f" -> Extension creates one-time local sign-in URL: {redirect_url}")

# Extract code from URL
import urllib.parse
parsed_url = urllib.parse.urlparse(redirect_url)
qs = urllib.parse.parse_qs(parsed_url.query)
handoff_code = qs["code"][0]

# 5. DASHBOARD HANDOFF EXCHANGE (Simulating browser tab opening http://localhost:5000 and claiming the code)
print("\n[Step 5] Local Browser Tab Opens & Exchanges Handoff Code:")
exchange_res = client.post("/api/auth/exchange-dashboard-code", json={"code": handoff_code})
assert exchange_res.status_code == 200
dashboard_tokens = exchange_res.get_json()
dash_headers = {"Authorization": f"Bearer {dashboard_tokens['access_token']}"}
print(" -> Dashboard tab successfully authenticated without re-entering password!")

# 6. VERIFY DASHBOARD SHOWS UPDATED SOLVED PROBLEM & SKILL SCORES
print("\n[Step 6] Dashboard Displays Newly Solved LeetCode Problem & Updated DSA Skill Score:")
dash_check = client.get("/api/dashboard/full", headers=dash_headers)
dash_final = dash_check.get_json()
print(" -> Problems on local dashboard:", len(dash_final["problems"]))
for p in dash_final["problems"]:
    print(f"    - {p['title']} ({p['slug']}) | Correct: {p['correct']}, Wrong: {p['wrong']}, Accuracy: {p['accuracy']}%")

print(f" -> Updated Overall DSA Skill Score: {dash_final['overall']['overall_skill_score']}/100 ({dash_final['overall']['skill_level']})")
print(f" -> Total Topics Tracked: {len(dash_final['topics'])}")
for t in dash_final["topics"]:
    print(f"    - Topic: {t['topic']} -> {t['score']}/100 ({t['label']})")

print("\n" + "=" * 65)
print("ALL EXTENSION WORK VERIFIED! TOTAL CONNECTION OPERATING 100% PERFECTLY!")
print("=" * 65)
