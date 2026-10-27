(function () {
  "use strict";

  var state = {
    stats: { correct: 0, wrong: 0 },
    history: [],
    problemStats: {},
    selectedIndex: 0,
  };
  var mode = "login";

  var authPanel = document.getElementById("authPanel");
  var appPanel = document.getElementById("appPanel");
  var loginTab = document.getElementById("loginTab");
  var signupTab = document.getElementById("signupTab");
  var nameInput = document.getElementById("nameInput");
  var emailInput = document.getElementById("emailInput");
  var passwordInput = document.getElementById("passwordInput");
  var authBtn = document.getElementById("authBtn");
  var authMessage = document.getElementById("authMessage");
  var userName = document.getElementById("userName");
  var syncStatus = document.getElementById("syncStatus");
  var correctCountEl = document.getElementById("correctCount");
  var wrongCountEl = document.getElementById("wrongCount");
  var accuracyEl = document.getElementById("accuracyValue");
  var historyEl = document.getElementById("history");
  var codeTitleEl = document.getElementById("codeTitle");
  var codeVerdictEl = document.getElementById("codeVerdict");
  var codeTimeEl = document.getElementById("codeTime");
  var codeViewEl = document.getElementById("codeView");
  var problemStatsEl = document.getElementById("problemStats");
  var skillScoreEl = document.getElementById("skillScore");
  var streakValEl = document.getElementById("streakVal");

  function send(message) {
    return new Promise(function (resolve, reject) {
      chrome.runtime.sendMessage(message, function (response) {
        if (chrome.runtime.lastError)
          return reject(new Error(chrome.runtime.lastError.message));
        resolve(response);
      });
    });
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // Accept millisecond timestamps, second timestamps, or ISO date strings.
  function normalizeTimestamp(value) {
    if (value == null || value === "") return 0;
    var numericValue = typeof value === "number" || /^\d+(?:\.\d+)?$/.test(String(value).trim());
    var n = numericValue ? Number(value) : Date.parse(value);
    if (!Number.isFinite(n)) n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return 0;
    // Unix timestamps in seconds are currently about 10 digits; milliseconds 13.
    return n < 100000000000 ? n * 1000 : n;
  }

  function formatTime(ts) {
    var normalized = normalizeTimestamp(ts);
    if (!normalized) return "Time unavailable";
    return new Date(normalized).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function normalizedTitle(value) {
    return String(value || "Untitled").trim().toLowerCase().replace(/\s+/g, " ");
  }

  function renderStats() {
    var correct = Number(state.stats.correct) || 0,
      wrong = Number(state.stats.wrong) || 0,
      total = correct + wrong;
    correctCountEl.textContent = correct;
    wrongCountEl.textContent = wrong;
    accuracyEl.textContent =
      (total ? Math.round((correct / total) * 100) : 0) + "%";
  }

  function renderProblemStats() {
    // Use history timestamps to infer recency for older problemStats records that
    // do not yet contain lastAttemptAt. Counts still come from problemStats.
    var latestByTitle = {};
    state.history.forEach(function (entry) {
      var titleKey = normalizedTitle(entry.title);
      var ts = normalizeTimestamp(entry.timestamp);
      if (ts > (latestByTitle[titleKey] || 0)) latestByTitle[titleKey] = ts;
    });

    var rows = Object.keys(state.problemStats || {})
      .map(function (key) {
        var p = state.problemStats[key] || {};
        var correct = Number(p.correct) || 0;
        var wrong = Number(p.wrong) || 0;
        var title = p.title || "Untitled";
        var recordedTime = normalizeTimestamp(p.lastAttemptAt || p.lastAttempt || p.updatedAt);
        var historyTime = latestByTitle[normalizedTitle(title)] || 0;
        return {
          title: title,
          correct: correct,
          wrong: wrong,
          attempts: correct + wrong,
          lastAttemptAt: Math.max(recordedTime, historyTime),
        };
      })
      // Most recently attempted questions first; use attempt count only as a
      // tie-breaker when timestamps are unavailable/equal.
      .sort(function (a, b) {
        return (b.lastAttemptAt - a.lastAttemptAt) || (b.attempts - a.attempts);
      })
      .slice(0, 3);
    problemStatsEl.innerHTML = rows.length
      ? ""
      : '<div class="problem-empty">No question statistics yet.</div>';
    rows.forEach(function (p) {
      var row = document.createElement("div");
      row.className = "problem-row";
      row.innerHTML =
        '<div class="problem-name">' +
        escapeHtml(p.title) +
        "</div>" +
        '<div class="problem-result"><span class="p-correct">✓ ' +
        p.correct +
        '</span><span class="p-wrong">✗ ' +
        p.wrong +
        "</span><span>" +
        p.attempts +
        " attempts</span></div>";
      problemStatsEl.appendChild(row);
    });
  }

  function renderHistory() {
    historyEl.innerHTML = "";
    if (!state.history.length) {
      historyEl.innerHTML = '<div class="empty">Nothing tracked yet.</div>';
      return;
    }
    state.history.forEach(function (entry, i) {
      var item = document.createElement("button");
      item.type = "button";
      item.className =
        "history-item" + (i === state.selectedIndex ? " active" : "");
      item.innerHTML =
        '<span class="dot ' +
        (entry.verdict === "Accepted" ? "ok" : "bad") +
        '"></span><span class="h-title">' +
        escapeHtml(entry.title || "Untitled") +
        "</span>";
      item.addEventListener("click", function () {
        state.selectedIndex = i;
        renderHistory();
        renderCode();
      });
      historyEl.appendChild(item);
    });
  }

  function renderCode() {
    var entry = state.history[state.selectedIndex];
    if (!entry) {
      codeTitleEl.textContent = "No submissions yet";
      codeVerdictEl.textContent = "";
      codeTimeEl.textContent = "";
      codeViewEl.innerHTML =
        '<p class="empty-note">Solve a problem on LeetCode and hit Submit.</p>';
      return;
    }
    codeTitleEl.textContent = entry.title || "Untitled";
    var verdict = entry.verdict || "Unknown";
    codeVerdictEl.textContent = verdict;
    codeVerdictEl.className =
      "verdict " + (verdict === "Accepted" ? "ok" : "bad");
    codeTimeEl.textContent = formatTime(entry.timestamp);
    codeViewEl.innerHTML = (entry.code || "(no code captured)")
      .split("\n")
      .map(function (line) {
        return '<div class="code-line">' + escapeHtml(line) + "</div>";
      })
      .join("");
  }

  function loadLocal() {
    chrome.storage.local.get(
      ["stats", "history", "problemStats"],
      function (data) {
        if (chrome.runtime.lastError) {
          console.error("Unable to load local dashboard data:", chrome.runtime.lastError.message);
          return;
        }
        state.stats = data.stats || { correct: 0, wrong: 0 };
        state.history = (Array.isArray(data.history) ? data.history : [])
          .slice()
          .sort(function (a, b) {
            return normalizeTimestamp(b && b.timestamp) - normalizeTimestamp(a && a.timestamp);
          });
        state.problemStats = data.problemStats && typeof data.problemStats === "object"
          ? data.problemStats
          : {};
        if (state.selectedIndex < 0 || state.selectedIndex >= state.history.length)
          state.selectedIndex = 0;
        renderStats();
        renderProblemStats();
        renderHistory();
        renderCode();
      }
    );
  }

  async function loadSkillScore() {
    try {
      var result = await send({ action: "apiRequest", path: "/dashboard/full" });
      if (result && result.ok && result.data) {
        var d = result.data;
        skillScoreEl.textContent = d.overall && d.overall.overall_skill_score != null
          ? d.overall.overall_skill_score
          : "—";
        streakValEl.textContent = d.overall && d.overall.streak_days != null
          ? d.overall.streak_days
          : "0";
      }
    } catch (e) {
      // Skill score not critical - silently fail
    }
  }

  async function checkAuth() {
    var data = await new Promise(function (resolve) {
      chrome.storage.local.get(["authToken", "user"], resolve);
    });
    if (!data.authToken) {
      authPanel.classList.remove("hidden");
      appPanel.classList.add("hidden");
      return;
    }
    try {
      var result = await send({ action: "apiRequest", path: "/me" });
      if (!result || !result.ok || !result.data) throw new Error((result && result.reason) || "Session expired");
      authPanel.classList.add("hidden");
      appPanel.classList.remove("hidden");
      var displayName = result.data.name || result.data.email || "User";
      userName.textContent = displayName[0].toUpperCase() + displayName.slice(1);
      // Load skill score from backend
      loadSkillScore();
    } catch (e) {
      await send({ action: "clearAuth" });
      authPanel.classList.remove("hidden");
      appPanel.classList.add("hidden");
    }
  }

  function setMode(next) {
    mode = next;
    var signup = mode === "signup";
    loginTab.classList.toggle("active", !signup);
    signupTab.classList.toggle("active", signup);
    nameInput.classList.toggle("hidden", !signup);
    authBtn.textContent = signup ? "Create account" : "Login";
    authMessage.textContent = "";
  }

  async function authenticate() {
    var email = emailInput.value.trim(),
      password = passwordInput.value,
      name = nameInput.value.trim();
    if (!email || !password || (mode === "signup" && !name)) {
      authMessage.textContent = "Fill in all required fields.";
      return;
    }
    if (mode === "signup" && password.length < 8) {
      authMessage.textContent = "Password must be at least 8 characters.";
      return;
    }
    authBtn.disabled = true;
    authMessage.textContent =
      mode === "signup" ? "Creating account..." : "Logging in...";
    try {
      var result = await send({
        action: "apiRequest",
        path: mode === "signup" ? "/auth/register" : "/auth/login",
        options: {
          method: "POST",
          body: JSON.stringify({ email: email, password: password, name: name }),
        },
      });
      if (!result || !result.ok || !result.data || !result.data.access_token) {
        throw new Error((result && result.reason) || "Authentication failed: invalid server response.");
      }
      await send({
        action: "saveAuth",
        token: result.data.access_token,
        refreshToken: result.data.refresh_token,
      });
      authMessage.textContent = "";
      await checkAuth();
    } catch (e) {
      authMessage.textContent = e.message;
    } finally {
      authBtn.disabled = false;
    }
  }

  loginTab.addEventListener("click", function () { setMode("login"); });
  signupTab.addEventListener("click", function () { setMode("signup"); });
  authBtn.addEventListener("click", authenticate);
  passwordInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") authenticate();
  });

  document.getElementById("logoutBtn").addEventListener("click", async function () {
    await send({ action: "clearAuth" });
    checkAuth();
  });

  document.getElementById("dashboardBtn").addEventListener("click", async function () {
    syncStatus.textContent = "Opening dashboard...";
    try {
      var result = await send({ action: "openDashboard" });
      syncStatus.textContent = result && result.ok
        ? "Dashboard opened."
        : "Dashboard: " + ((result && result.reason) || "login required");
    } catch (e) {
      syncStatus.textContent = "Dashboard: " + (e.message || "Unable to open dashboard");
    }
  });

  document.getElementById("resetBtn").addEventListener("click", function () {
    if (!confirm("Clear local attempt history? Server data will not be deleted.")) return;
    chrome.storage.local.set(
      { stats: { correct: 0, wrong: 0 }, history: [], problemStats: {} },
      loadLocal,
    );
  });

  document.getElementById("copyBtn").addEventListener("click", function () {
    var entry = state.history[state.selectedIndex];
    if (!entry) return;
    var copyBtn = document.getElementById("copyBtn");
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      copyBtn.textContent = "Clipboard unavailable";
      return;
    }
    navigator.clipboard.writeText(entry.code || "").then(function () {
      var old = copyBtn.textContent;
      copyBtn.textContent = "Copied";
      setTimeout(function () { copyBtn.textContent = old; }, 1000);
    }).catch(function () {
      copyBtn.textContent = "Copy failed";
    });
  });

  chrome.storage.onChanged.addListener(function (changes, area) {
    if (area === "local" && (changes.stats || changes.history || changes.problemStats)) loadLocal();
  });

  loadLocal();
  checkAuth();
})();