(function () {
  const API = window.LEARNSENSE_API_BASE;
  const $ = (id) => document.getElementById(id);

  function token() {
    return localStorage.getItem("learnsense_access_token") || "";
  }

  async function api(path, options = {}) {
    const headers = Object.assign(
      { "Content-Type": "application/json" },
      options.headers || {},
    );
    if (token()) headers.Authorization = "Bearer " + token();
    let r = await fetch(API + path, { ...options, headers });
    if (r.status === 401 && path !== "/auth/refresh") {
      const refresh = localStorage.getItem("learnsense_refresh_token") || "";
      if (refresh) {
        const refreshResponse = await fetch(API + "/auth/refresh", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: "Bearer " + refresh,
          },
        });
        const refreshBody = await refreshResponse.json().catch(() => ({}));
        if (refreshResponse.ok && refreshBody.access_token) {
          localStorage.setItem(
            "learnsense_access_token",
            refreshBody.access_token,
          );
          headers.Authorization = "Bearer " + refreshBody.access_token;
          r = await fetch(API + path, { ...options, headers });
        }
      }
    }
    const b = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(b.error || "Request failed");
    return b;
  }

  function fmt(s) {
    return new Date(s).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  }

  // ============================================================
  // Tab navigation
  // ============================================================
  function initTabs() {
    const tabButtons = document.querySelectorAll(".tab[data-tab]");
    tabButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        // Deactivate all tabs and panels
        tabButtons.forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach((s) => s.classList.remove("active"));
        // Activate the clicked tab and its panel
        btn.classList.add("active");
        const panel = $("tab-" + btn.dataset.tab);
        if (panel) panel.classList.add("active");
        // Lazy-load tab content
        const tab = btn.dataset.tab;
        if (tab === "skills") loadSkills();
        if (tab === "report") loadReport();
        if (tab === "problems") loadAllProblems();
        if (tab === "goals") loadGoals();
      });
    });
  }

  // ============================================================
  // Populate problem rows into a <tbody> element
  // ============================================================
  function renderProblemRows(tbody, problems) {
    tbody.innerHTML = "";
    problems.forEach((p) => {
      const tr = document.createElement("tr");
      tr.innerHTML =
        '<td><button class="problem-link"></button></td><td class="good">' +
        p.correct +
        '</td><td class="bad">' +
        p.wrong +
        "</td><td>" +
        p.attempts +
        "</td><td>" +
        p.accuracy +
        "%</td><td>" +
        fmt(p.last_solved_at) +
        "</td>";
      tr.querySelector("button").textContent = p.title;
      tr.querySelector("button").onclick = () => showProblem(p.slug);
      tbody.appendChild(tr);
    });
  }

  // ============================================================
  // Main load – Overview tab
  // ============================================================
  let cachedFullData = null;

  async function load() {
    if (!token()) {
      location.href = "extension-login.html";
      return;
    }
    try {
      // Use /dashboard/full for richer data (skill score, streak, etc.)
      const me = await api("/me");
      if ($("user")) $("user").textContent = me.email;

      let data;
      let usedFull = false;
      try {
        data = await api("/dashboard/full");
        usedFull = true;
      } catch (fullErr) {
        // Fallback to /dashboard/summary if /dashboard/full fails
        // (e.g. missing tables before migration)
        console.warn("dashboard/full failed, falling back to summary:", fullErr.message);
        const summaryData = await api("/dashboard/summary");
        data = {
          overall: {
            ...summaryData.overall,
            overall_skill_score: null,
            streak_days: 0,
          },
          problems: summaryData.problems,
          topics: [],
          report_status: "none",
        };
      }
      cachedFullData = data;

      // Hero card
      if ($("hero-score"))
        $("hero-score").textContent =
          data.overall.overall_skill_score != null
            ? data.overall.overall_skill_score
            : "—";
      if ($("streak-val"))
        $("streak-val").textContent = data.overall.streak_days || 0;
      if ($("solved-val"))
        $("solved-val").textContent = data.overall.solved_problems || 0;
      if ($("accuracy-val"))
        $("accuracy-val").textContent = (data.overall.accuracy || 0) + "%";

      // Stat cards
      if ($("stat-solved"))
        $("stat-solved").textContent = data.overall.correct + data.overall.wrong || 0;
      if ($("stat-correct"))
        $("stat-correct").textContent = data.overall.correct || 0;
      if ($("stat-wrong"))
        $("stat-wrong").textContent = data.overall.wrong || 0;
      if ($("stat-accuracy"))
        $("stat-accuracy").textContent = (data.overall.accuracy || 0) + "%";

      // Overview problems table
      const overviewBody = $("overview-problems");
      if (overviewBody) renderProblemRows(overviewBody, data.problems);

      if ($("overview-status"))
        $("overview-status").textContent = data.problems.length + " problems";
    } catch (e) {
      if (
        e.message.toLowerCase().includes("token") ||
        e.message.toLowerCase().includes("auth")
      ) {
        localStorage.removeItem("learnsense_access_token");
        location.href = "extension-login.html";
      } else {
        if ($("overview-status")) $("overview-status").textContent = e.message;
      }
    }
  }

  // ============================================================
  // Show a specific problem's solution in the right panel
  // ============================================================
  async function showProblem(slug) {
    try {
      const d = await api("/problems/" + encodeURIComponent(slug));
      const s = d.submissions[0];

      if ($("solution-meta"))
        $("solution-meta").textContent =
          d.problem.title + " · " + s.language + " · " + fmt(s.submitted_at);

      if ($("code-view"))
        $("code-view").textContent = s.code || "(empty code)";

      // Scroll to the code panel
      const codePanel = $("code-panel");
      if (codePanel) {
        setTimeout(() => {
          codePanel.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 100);
      }
    } catch (e) {
      if ($("solution-meta")) $("solution-meta").textContent = e.message;
    }
  }

  // ============================================================
  // Skills tab
  // ============================================================
  let skillsLoaded = false;
  async function loadSkills() {
    if (skillsLoaded) return;
    try {
      const data = await api("/skills");
      skillsLoaded = true;

      if ($("skills-overall"))
        $("skills-overall").textContent =
          data.overall_score != null ? data.overall_score : "—";

      const grid = $("topic-grid");
      if (!grid) return;
      grid.innerHTML = "";

      if (!data.topics || data.topics.length === 0) {
        grid.innerHTML =
          '<div class="loading-msg">No skill data yet. Solve problems to see your skill scores.</div>';
        return;
      }

      data.topics.forEach((t) => {
        const card = document.createElement("div");
        card.className = "topic-card";
        const barWidth = Math.min(100, Math.max(0, t.score));
        card.innerHTML =
          '<div class="topic-name">' +
          escapeHtml(t.topic) +
          "</div>" +
          '<div class="topic-bar"><div class="topic-fill" style="width:' +
          barWidth +
          '%"></div></div>' +
          '<div class="topic-score">' +
          t.score +
          " / 100</div>" +
          '<div class="topic-meta">' +
          t.problems_seen +
          " problems · " +
          Math.round(t.confidence * 100) +
          "% confidence</div>";
        grid.appendChild(card);
      });
    } catch (e) {
      const grid = $("topic-grid");
      if (grid) grid.innerHTML = '<div class="loading-msg">Failed to load skills: ' + escapeHtml(e.message) + "</div>";
    }
  }

  // ============================================================
  // AI Report tab
  // ============================================================
  let reportLoaded = false;
  async function loadReport() {
    if (reportLoaded) return;
    try {
      const data = await api("/report");
      if (data.status === "pending" || data.status === "generating") {
        if ($("report-loading"))
          $("report-loading").textContent =
            "Report is being generated... Refresh in a minute.";
        return;
      }
      reportLoaded = true;

      if (data.status === "done" && data.report) {
        renderReport(data.report, data.generated_at, data.model);
      }
    } catch (e) {
      if ($("report-loading"))
        $("report-loading").textContent = "Failed to load report: " + e.message;
    }
  }

  function renderReport(report, generatedAt, model) {
    if ($("report-meta")) {
      let meta = "Personalized analysis from your practice data";
      if (generatedAt) meta += " · Generated " + fmt(generatedAt);
      if (model) meta += " · " + model;
      $("report-meta").textContent = meta;
    }

    const container = $("report-content");
    if (!container) return;
    container.innerHTML = "";

    // Helper to render a section
    function addSection(title, content) {
      const sec = document.createElement("div");
      sec.className = "report-section";
      sec.innerHTML = "<h3>" + escapeHtml(title) + "</h3>";
      if (typeof content === "string") {
        const p = document.createElement("p");
        p.textContent = content;
        sec.appendChild(p);
      } else if (Array.isArray(content)) {
        const ul = document.createElement("ul");
        content.forEach((item) => {
          const li = document.createElement("li");
          if (typeof item === "string") {
            li.textContent = item;
          } else if (item.topic) {
            li.textContent =
              item.topic +
              " (" +
              (item.priority || "") +
              "): " +
              (item.reason || "");
          } else {
            li.textContent = JSON.stringify(item);
          }
          ul.appendChild(li);
        });
        sec.appendChild(ul);
      }
      container.appendChild(sec);
    }

    if (report.skill_summary) addSection("Summary", report.skill_summary);
    if (report.strengths) addSection("Strengths", report.strengths);
    if (report.weaknesses) addSection("Areas to Improve", report.weaknesses);
    if (report.top_patterns) addSection("Top Patterns", report.top_patterns);
    if (report.recommendations)
      addSection("Recommendations", report.recommendations);
    if (report.learning_path)
      addSection("Suggested Learning Path", report.learning_path);
    if (report.weekly_target) addSection("Weekly Target", report.weekly_target);
    if (report.encouragement) addSection("💪 Encouragement", report.encouragement);
  }

  // ============================================================
  // All Problems tab
  // ============================================================
  let allProblemsLoaded = false;
  let allProblemsData = [];
  async function loadAllProblems() {
    if (allProblemsLoaded && allProblemsData.length) {
      return;
    }
    try {
      // Use cached data if available, otherwise fetch
      if (cachedFullData && cachedFullData.problems) {
        allProblemsData = cachedFullData.problems;
      } else {
        const data = await api("/dashboard/summary");
        allProblemsData = data.problems;
      }
      allProblemsLoaded = true;
      renderAllProblems(allProblemsData);
    } catch (e) {
      const body = $("all-problems");
      if (body) {
        body.innerHTML =
          "<tr><td colspan='6'>Failed to load: " +
          escapeHtml(e.message) +
          "</td></tr>";
      }
    }
  }

  function renderAllProblems(problems) {
    const body = $("all-problems");
    if (!body) return;
    renderProblemRows(body, problems);
  }

  // Problem search/filter
  function initProblemSearch() {
    const searchInput = $("problem-search");
    if (!searchInput) return;
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.toLowerCase();
      const filtered = allProblemsData.filter((p) =>
        p.title.toLowerCase().includes(q),
      );
      renderAllProblems(filtered);
    });
  }

  // ============================================================
  // Goals tab
  // ============================================================
  let goalsLoaded = false;
  async function loadGoals() {
    if (goalsLoaded) return;
    try {
      const data = await api("/goals");
      goalsLoaded = true;
      if (data.goal) {
        if ($("goal-type")) $("goal-type").value = data.goal.type || "general";
        if ($("goal-daily"))
          $("goal-daily").value = data.goal.daily_target_minutes || "";
        if ($("goal-date"))
          $("goal-date").value = data.goal.target_date || "";
        if ($("goal-notes"))
          $("goal-notes").value = data.goal.notes || "";
      }
    } catch (e) {
      if ($("goal-msg")) $("goal-msg").textContent = "Failed to load goals.";
    }
  }

  async function saveGoal() {
    try {
      const body = {
        type: $("goal-type") ? $("goal-type").value : "general",
        daily_target_minutes: $("goal-daily")
          ? parseInt($("goal-daily").value) || null
          : null,
        notes: $("goal-notes") ? $("goal-notes").value : "",
      };
      await api("/goals", {
        method: "PUT",
        body: JSON.stringify(body),
      });
      if ($("goal-msg")) {
        $("goal-msg").textContent = "Goal saved!";
        $("goal-msg").className = "muted success";
        setTimeout(() => {
          $("goal-msg").textContent = "";
          $("goal-msg").className = "muted";
        }, 3000);
      }
    } catch (e) {
      if ($("goal-msg")) {
        $("goal-msg").textContent = "Failed to save: " + e.message;
        $("goal-msg").className = "muted error";
      }
    }
  }

  // ============================================================
  // Regenerate AI report
  // ============================================================
  async function regenerateReport() {
    const btn = $("regen-btn");
    if (btn) btn.disabled = true;
    try {
      await api("/report/regenerate", { method: "POST" });
      reportLoaded = false;
      if ($("report-content"))
        $("report-content").innerHTML =
          '<div class="loading-msg">Regenerating report... Refresh in a minute.</div>';
      // Try loading after a short delay
      setTimeout(() => loadReport(), 5000);
    } catch (e) {
      if ($("report-content"))
        $("report-content").innerHTML =
          '<div class="loading-msg">Failed: ' + escapeHtml(e.message) + "</div>";
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // ============================================================
  // Utility
  // ============================================================
  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ============================================================
  // Extension login handler (for extension-login.html)
  // ============================================================
  window.handleExtensionLogin = async function () {
    const p = new URLSearchParams(location.search);
    const code = p.get("code");
    if (!code) {
      $("message").textContent = "Missing sign-in code.";
      $("message").className = "error";
      return;
    }
    try {
      const r = await fetch(API + "/auth/exchange-dashboard-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const b = await r.json();
      if (!r.ok) throw new Error(b.error || "Sign-in failed");
      localStorage.setItem("learnsense_access_token", b.access_token);
      localStorage.setItem("learnsense_refresh_token", b.refresh_token || "");
      location.replace("index.html");
    } catch (e) {
      $("message").textContent = e.message;
      $("message").className = "error";
    }
  };

  // ============================================================
  // Wire up event listeners & boot
  // ============================================================
  if ($("refresh")) $("refresh").onclick = () => {
    // Reset caches and reload everything
    cachedFullData = null;
    skillsLoaded = false;
    reportLoaded = false;
    allProblemsLoaded = false;
    goalsLoaded = false;
    load();
  };

  if ($("logout"))
    $("logout").onclick = function () {
      localStorage.removeItem("learnsense_access_token");
      localStorage.removeItem("learnsense_refresh_token");
      location.href = "extension-login.html";
    };

  if ($("save-goal")) $("save-goal").onclick = saveGoal;
  if ($("regen-btn")) $("regen-btn").onclick = regenerateReport;

  // Initialize tabs
  initTabs();
  initProblemSearch();

  // Boot: only load on dashboard (not on extension-login.html)
  if (
    location.pathname.endsWith("index.html") ||
    location.pathname.endsWith("/dashboard/") ||
    location.pathname.endsWith("/dashboard") ||
    location.pathname.endsWith("/")
  )
    load();
})();
