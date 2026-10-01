(function () {
  "use strict";

  var state = {
    stats: { correct: 0, wrong: 0 },
    history: [],
    problemStats: {},
    selectedIndex: 0,
  };
  var mode = "login";
  var $ = function (id) { return document.getElementById(id); };
  var authPanel = $("authPanel");
  var appPanel = $("appPanel");
  var loginTab = $("loginTab");
  var signupTab = $("signupTab");
  var nameInput = $("nameInput");
  var emailInput = $("emailInput");
  var passwordInput = $("passwordInput");
  var authBtn = $("authBtn");
  var authMessage = $("authMessage");

  function send(message) {
    return new Promise(function (resolve, reject) {
      chrome.runtime.sendMessage(message, function (response) {
        if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
        resolve(response);
      });
    });
  }

  function escapeHtml(value) {
    return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function render() {
    var correct = state.stats.correct || 0;
    var wrong = state.stats.wrong || 0;
    var total = correct + wrong;
    $("correctCount").textContent = correct;
    $("wrongCount").textContent = wrong;
    $("accuracyValue").textContent = (total ? Math.round(correct / total * 100) : 0) + "%";

    var stats = Object.keys(state.problemStats).map(function (key) {
      var item = state.problemStats[key];
      return {
        title: item.title || "Untitled",
        correct: item.correct || 0,
        wrong: item.wrong || 0,
      };
    }).sort(function (a, b) {
      return (b.correct + b.wrong) - (a.correct + a.wrong);
    }).slice(0, 5);
    var statsEl = $("problemStats");
    statsEl.innerHTML = stats.length ? "" : '<div class="problem-empty">No question statistics yet.</div>';
    stats.forEach(function (item) {
      var row = document.createElement("div");
      row.className = "problem-row";
      row.innerHTML = '<div class="problem-name">' + escapeHtml(item.title) + "</div>" +
        '<div class="problem-result"><span class="p-correct">✓ ' + item.correct +
        '</span><span class="p-wrong">✗ ' + item.wrong + "</span><span>" +
        (item.correct + item.wrong) + " attempts</span></div>";
      statsEl.appendChild(row);
    });

    var historyEl = $("history");
    historyEl.innerHTML = "";
    if (!state.history.length) {
      historyEl.innerHTML = '<div class="empty">Nothing tracked yet.</div>';
    } else {
      state.history.forEach(function (entry, index) {
        var item = document.createElement("button");
        item.type = "button";
        item.className = "history-item" + (index === state.selectedIndex ? " active" : "");
        item.innerHTML = '<span class="dot ' + (entry.verdict === "Accepted" ? "ok" : "bad") +
          '"></span><span class="h-title">' + escapeHtml(entry.title || "Untitled") + "</span>";
        item.addEventListener("click", function () {
          state.selectedIndex = index;
          render();
        });
        historyEl.appendChild(item);
      });
    }

    var entry = state.history[state.selectedIndex];
    if (!entry) {
      $("codeTitle").textContent = "No submissions yet";
      $("codeVerdict").textContent = "";
      $("codeTime").textContent = "";
      $("codeView").innerHTML = '<p class="empty-note">Solve a problem on LeetCode, CodeChef, or HackerRank and hit Submit.</p>';
      return;
    }
    $("codeTitle").textContent = entry.title || "Untitled";
    $("codeVerdict").textContent = entry.verdict;
    $("codeVerdict").className = "verdict " + (entry.verdict === "Accepted" ? "ok" : "bad");
    $("codeTime").textContent = new Date(entry.timestamp).toLocaleString();
    $("codeView").innerHTML = (entry.code || "(no code captured)").split("\n").map(function (line) {
      return '<div class="code-line">' + escapeHtml(line) + "</div>";
    }).join("");
  }

  function loadLocal() {
    chrome.storage.local.get(["stats", "history", "problemStats"], function (data) {
      state.stats = data.stats || { correct: 0, wrong: 0 };
      state.history = data.history || [];
      state.problemStats = data.problemStats || {};
      if (state.selectedIndex >= state.history.length) state.selectedIndex = 0;
      render();
    });
  }

  async function checkAuth() {
    var data = await new Promise(function (resolve) {
      chrome.storage.local.get(["authToken"], resolve);
    });
    if (!data.authToken) {
      authPanel.classList.remove("hidden");
      appPanel.classList.add("hidden");
      return;
    }
    try {
      var result = await send({ action: "apiRequest", path: "/me" });
      if (!result.ok || !result.data || !result.data.email) throw new Error(result.reason || "Session expired");
      authPanel.classList.add("hidden");
      appPanel.classList.remove("hidden");
      $("userEmail").textContent = result.data.email;
    } catch (error) {
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
    var email = emailInput.value.trim();
    var password = passwordInput.value;
    var name = nameInput.value.trim();
    if (!email || !password || (mode === "signup" && !name)) {
      authMessage.textContent = "Fill in all required fields.";
      return;
    }
    if (mode === "signup" && password.length < 8) {
      authMessage.textContent = "Password must be at least 8 characters.";
      return;
    }
    authBtn.disabled = true;
    authMessage.textContent = mode === "signup" ? "Creating account..." : "Logging in...";
    try {
      var result = await send({
        action: "apiRequest",
        path: mode === "signup" ? "/auth/register" : "/auth/login",
        options: {
          method: "POST",
          body: JSON.stringify({ email: email, password: password, name: name }),
        },
      });
      if (!result || !result.ok) throw new Error((result && result.reason) || "Authentication failed");
      if (!result.data || !result.data.access_token || !result.data.user) {
        throw new Error("The server returned an incomplete authentication response.");
      }
      await send({
        action: "saveAuth",
        token: result.data.access_token,
        refreshToken: result.data.refresh_token || "",
      });
      await checkAuth();
    } catch (error) {
      authMessage.textContent = error.message;
    } finally {
      authBtn.disabled = false;
    }
  }

  loginTab.addEventListener("click", function () { setMode("login"); });
  signupTab.addEventListener("click", function () { setMode("signup"); });
  authBtn.addEventListener("click", authenticate);
  passwordInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") authenticate();
  });
  $("logoutBtn").addEventListener("click", async function () {
    await send({ action: "clearAuth" });
    setMode("login");
    await checkAuth();
  });
  $("dashboardBtn").addEventListener("click", async function () {
    $("syncStatus").textContent = "Opening dashboard...";
    var result = await send({ action: "openDashboard" });
    $("syncStatus").textContent = result.ok ? "Dashboard opened." : "Dashboard: " + (result.reason || "login required");
  });
  $("resetBtn").addEventListener("click", function () {
    if (confirm("Clear local attempt history? Server data will not be deleted.")) {
      chrome.storage.local.set({ stats: { correct: 0, wrong: 0 }, history: [], problemStats: {} }, loadLocal);
    }
  });
  $("copyBtn").addEventListener("click", function () {
    var entry = state.history[state.selectedIndex];
    if (entry) navigator.clipboard.writeText(entry.code || "");
  });
  chrome.storage.onChanged.addListener(function (changes, area) {
    if (area === "local" && (changes.stats || changes.history || changes.problemStats)) loadLocal();
  });
  loadLocal();
  checkAuth();
})();
