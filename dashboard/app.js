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
      const isOptimal = p.is_optimal !== false;
      const timeC = p.time_complexity || "O(n)";
      const spaceC = p.space_complexity || "O(1)";
      const expTime = p.expected_time_complexity || timeC;
      const compLabel = timeC + (isOptimal ? " · Optimal" : " · Suboptimal");
      const badgeClass = isOptimal ? "optimal" : "suboptimal";
      const tooltip = "Time: " + timeC + ", Space: " + spaceC + (isOptimal ? " (Optimal Approach)" : " (Expected: " + expTime + ")");

      const tr = document.createElement("tr");
      tr.innerHTML =
        '<td class="col-problem"><button class="problem-link"></button></td>' +
        '<td class="good col-num">' + p.correct + '</td>' +
        '<td class="bad col-num">' + p.wrong + '</td>' +
        '<td class="col-num">' + p.attempts + '</td>' +
        '<td class="col-num">' + p.accuracy + '%</td>' +
        '<td class="col-complexity"><span class="complexity-badge ' + badgeClass + '" title="' + escapeHtml(tooltip) + '"><span class="c-dot"></span>' +
        escapeHtml(compLabel) +
        '</span></td>' +
        '<td class="col-date">' + fmt(p.last_solved_at) + '</td>';
      const btn = tr.querySelector("button");
      btn.textContent = p.title;
      btn.title = p.title;
      btn.onclick = () => showProblem(p.slug);
      tbody.appendChild(tr);
    });
  }

  // ============================================================
  // Main load – Overview tab
  // ============================================================
  let cachedFullData = null;
  let cachedUserData = null;
  let cachedReportData = null;
  let cachedSkillsData = null;
  let cachedGoalsData = null;

  async function load() {
    if (!token()) {
      location.href = "extension-login.html";
      return;
    }
    try {
      // Use /dashboard/full for richer data (skill score, streak, etc.)
      const me = await api("/me");
      cachedUserData = me;
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
      if ($("hero-score")) {
        const scoreVal = data.overall.overall_skill_score != null ? data.overall.overall_skill_score : "—";
        $("hero-score").textContent = scoreVal;
        if ($("hero-ring") && scoreVal !== "—") {
          $("hero-ring").style.setProperty("--pct", Math.min(100, Math.max(0, scoreVal)) + "%");
        }
      }
      if ($("hero-tier")) {
        const s = data.overall.overall_skill_score;
        let tier = "DSA Skill Score";
        if (s != null) {
          if (s >= 85) tier = "Expert (" + s + ")";
          else if (s >= 70) tier = "Proficient (" + s + ")";
          else if (s >= 55) tier = "Developing (" + s + ")";
          else if (s >= 35) tier = "Beginner (" + s + ")";
          else tier = "Novice (" + s + ")";
        }
        $("hero-tier").textContent = tier;
      }
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
  let currentProblemSlug = null;
  let activeCodeTab = "your"; // "your" or "expected"

  async function showProblem(slug) {
    currentProblemSlug = slug;
    try {
      if ($("solution-meta")) $("solution-meta").textContent = "Loading solution & AI analysis...";
      const d = await api("/problems/" + encodeURIComponent(slug));
      const s = d.submissions && d.submissions.length ? d.submissions[0] : null;
      if (!s) {
        if ($("solution-meta")) $("solution-meta").textContent = d.problem.title + " · No submissions found";
        return;
      }
      const ev = d.evaluation || {};

      if ($("solution-meta"))
        $("solution-meta").textContent =
          d.problem.title + " · " + s.language + " · " + fmt(s.submitted_at);

      // Show AI Complexity Card, Tabs, and Re-analyze button
      if ($("ai-complexity-card")) $("ai-complexity-card").style.display = "flex";
      if ($("code-tabs-bar")) $("code-tabs-bar").style.display = "flex";
      if ($("ai-reanalyze-btn")) {
        $("ai-reanalyze-btn").style.display = "inline-block";
        $("ai-reanalyze-btn").onclick = () => reanalyzeProblem(slug);
      }

      // Optimality Banner
      const isOptimal = ev.is_optimal !== false;
      const optBanner = $("optimality-banner");
      if (optBanner) {
        optBanner.className = isOptimal ? "optimality-banner" : "optimality-banner suboptimal";
      }
      if ($("opt-icon")) $("opt-icon").textContent = isOptimal ? "✅" : "⚠️";
      if ($("opt-title")) {
        $("opt-title").textContent = isOptimal ? "Optimal Solution" : "Suboptimal Solution";
      }
      if ($("opt-subtitle")) {
        $("opt-subtitle").textContent = isOptimal
          ? "Your solution achieves optimal theoretical time and space complexity bounds."
          : "Your solution is valid, but can be optimized to " + (ev.expected_time_complexity || "O(n)") + " time / " + (ev.expected_space_complexity || "O(1)") + " space.";
      }

      // Complexity metrics
      if ($("your-time-comp")) $("your-time-comp").textContent = ev.time_complexity || "O(n)";
      if ($("your-space-comp")) $("your-space-comp").textContent = ev.space_complexity || "O(1)";
      if ($("exp-time-comp")) $("exp-time-comp").textContent = ev.expected_time_complexity || ev.time_complexity || "O(n)";
      if ($("exp-space-comp")) $("exp-space-comp").textContent = ev.expected_space_complexity || ev.space_complexity || "O(1)";

      // AI Thought
      if ($("pattern-tag")) $("pattern-tag").textContent = isOptimal ? "Optimal Approach" : "Optimization Opportunity";
      if ($("ai-thought-text")) {
        $("ai-thought-text").textContent = ev.ai_thought || "AI verified time and space algorithmic bounds.";
      }

      // Code views
      if ($("code-view")) $("code-view").textContent = s.code || "(empty code)";
      if ($("expected-code-view")) {
        $("expected-code-view").textContent = ev.expected_solution || s.code || "// No expected solution available";
      }

      // Reset tab view to "Your Solution"
      switchCodeTab("your");

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

  function switchCodeTab(tab) {
    activeCodeTab = tab;
    const yourBtn = $("tab-your-code");
    const expBtn = $("tab-expected-code");
    const yourView = $("code-view");
    const expView = $("expected-code-view");

    if (tab === "your") {
      if (yourBtn) yourBtn.classList.add("active");
      if (expBtn) expBtn.classList.remove("active");
      if (yourView) yourView.style.display = "block";
      if (expView) expView.style.display = "none";
    } else {
      if (yourBtn) yourBtn.classList.remove("active");
      if (expBtn) expBtn.classList.add("active");
      if (yourView) yourView.style.display = "none";
      if (expView) expView.style.display = "block";
    }
  }

  async function reanalyzeProblem(slug) {
    const btn = $("ai-reanalyze-btn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "⏳ Analyzing...";
    }
    try {
      const res = await api("/problems/" + encodeURIComponent(slug) + "/analyze", {
        method: "POST",
      });
      if (res && res.evaluation) {
        await showProblem(slug);
      }
    } catch (e) {
      alert("AI analysis error: " + e.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "⚡ AI Analyze";
      }
    }
  }

  function initCodeTabs() {
    const yourBtn = $("tab-your-code");
    const expBtn = $("tab-expected-code");
    const copyBtn = $("copy-code-btn");

    if (yourBtn) yourBtn.onclick = () => switchCodeTab("your");
    if (expBtn) expBtn.onclick = () => switchCodeTab("expected");
    if (copyBtn) {
      copyBtn.onclick = () => {
        const text =
          activeCodeTab === "your"
            ? ($("code-view") ? $("code-view").textContent : "")
            : ($("expected-code-view") ? $("expected-code-view").textContent : "");
        if (text) {
          navigator.clipboard
            .writeText(text)
            .then(() => {
              copyBtn.textContent = "✅ Copied!";
              setTimeout(() => {
                copyBtn.textContent = "📋 Copy";
              }, 1800);
            })
            .catch(() => {});
        }
      };
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
      cachedSkillsData = data;
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
        const labelText = t.label || "Developing";
        const labelClass = "label-" + labelText.toLowerCase();
        const confPct = Math.round((t.confidence || 0) * 100);
        card.innerHTML =
          '<div class="tc-name">' + escapeHtml(t.topic) + '</div>' +
          '<div class="tc-score">' + t.score + ' <span style="font-size:12px;color:#7f8ba5;">/100</span></div>' +
          '<span class="tc-label ' + labelClass + '">' + escapeHtml(labelText) + '</span>' +
          '<div class="conf-bar">' +
            '<div class="conf-bar-label">Evaluation confidence: ' + confPct + '%</div>' +
            '<div class="conf-track"><div class="conf-fill" style="width:' + confPct + '%"></div></div>' +
          '</div>' +
          '<div class="tc-problems">' + (t.problems_seen || 1) + ' problem' + ((t.problems_seen || 1) > 1 ? 's' : '') + ' analyzed</div>';
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
  let reportPollingTimer = null;

  async function loadReport(retryCount = 0) {
    if (reportLoaded && retryCount === 0) return;
    try {
      const data = await api("/report");
      if (data.status === "pending" || data.status === "generating") {
        if ($("report-loading"))
          $("report-loading").textContent =
            "AI is analyzing your performance... (" + (retryCount + 1) + "s)";
        if (retryCount < 12) {
          clearTimeout(reportPollingTimer);
          reportPollingTimer = setTimeout(() => loadReport(retryCount + 1), 2500);
        } else {
          if ($("report-loading"))
            $("report-loading").textContent =
              "AI report generation taking longer than expected. Click Regenerate to retry.";
        }
        return;
      }
      reportLoaded = true;

      if (data.status === "done" && data.report) {
        cachedReportData = data;
        renderReport(data.report, data.generated_at, data.model);
      }
    } catch (e) {
      if ($("report-loading"))
        $("report-loading").textContent = "Failed to load report: " + e.message;
    }
  }

  function renderReport(report, generatedAt, model) {
    if ($("report-meta")) {
      let meta = "Personalized AI performance evaluation";
      if (generatedAt) meta += " · Generated " + fmt(generatedAt);
      if (model) meta += " · " + model;
      $("report-meta").textContent = meta;
    }

    const container = $("report-content");
    if (!container) return;
    container.innerHTML = "";

    const grid = document.createElement("div");
    grid.className = "report-grid";

    // Summary Card (Full width)
    if (report.skill_summary) {
      const card = document.createElement("div");
      card.className = "report-card full";
      const scoreBadge = report.overall_dsa_score != null
        ? '<span style="float:right;background:#7c6cff;color:#fff;padding:4px 10px;border-radius:8px;font-weight:700;font-size:12px;">Overall DSA Skill: ' + report.overall_dsa_score + '/100 (' + (report.skill_level || "Proficient") + ')</span>'
        : '';
      card.innerHTML = "<h3>AI Skill Summary " + scoreBadge + "</h3><p>" + escapeHtml(report.skill_summary) + "</p>";
      grid.appendChild(card);
    }

    // Strengths
    if (report.strengths && report.strengths.length) {
      const card = document.createElement("div");
      card.className = "report-card";
      card.innerHTML = "<h3>Key Strengths Identified</h3>";
      const ul = document.createElement("ul");
      report.strengths.forEach((s) => {
        const li = document.createElement("li");
        li.textContent = "✓ " + s;
        ul.appendChild(li);
      });
      card.appendChild(ul);
      grid.appendChild(card);
    }

    // Areas to Improve
    if (report.weaknesses && report.weaknesses.length) {
      const card = document.createElement("div");
      card.className = "report-card";
      card.innerHTML = "<h3>Areas for Growth & Gaps</h3>";
      const ul = document.createElement("ul");
      report.weaknesses.forEach((w) => {
        const li = document.createElement("li");
        li.textContent = "▲ " + w;
        ul.appendChild(li);
      });
      card.appendChild(ul);
      grid.appendChild(card);
    }

    // Recommendations
    if (report.recommendations && report.recommendations.length) {
      const card = document.createElement("div");
      card.className = "report-card full";
      card.innerHTML = "<h3>Recommended Practice Priorities</h3>";
      report.recommendations.forEach((rec) => {
        const item = document.createElement("div");
        item.className = "rec-item";
        const prio = (rec.priority || "high").toLowerCase();
        const prioColor = prio === "high" ? "#ff6b6b" : prio === "medium" ? "#f0b429" : "#58d68d";
        item.innerHTML =
          '<span class="rec-priority" style="color:' + prioColor + ';border:1px solid ' + prioColor + ';border-radius:4px;">' + (rec.priority || "high").toUpperCase() + '</span>' +
          '<div class="rec-topic">' + escapeHtml(rec.topic || "") + '</div>' +
          '<div class="rec-reason">' + escapeHtml(rec.reason || "") + '</div>';
        card.appendChild(item);
      });
      grid.appendChild(card);
    }

    // Learning Path
    if (report.learning_path && report.learning_path.length) {
      const card = document.createElement("div");
      card.className = "report-card";
      card.innerHTML = "<h3>Suggested Learning Path</h3>";
      const ol = document.createElement("ol");
      ol.style.paddingLeft = "20px";
      report.learning_path.forEach((step) => {
        const li = document.createElement("li");
        li.style.marginBottom = "6px";
        li.style.color = "#b0bcd0";
        li.textContent = step;
        ol.appendChild(li);
      });
      card.appendChild(ol);
      grid.appendChild(card);
    }

    // Weekly Target & Motivational Encouragement
    if (report.weekly_target || report.encouragement) {
      const card = document.createElement("div");
      card.className = "report-card";
      card.innerHTML = "<h3>Weekly Target & Coach Advice</h3>";
      if (report.weekly_target) {
        const p1 = document.createElement("p");
        p1.innerHTML = "<strong>🎯 Target:</strong> " + escapeHtml(report.weekly_target);
        p1.style.marginBottom = "10px";
        card.appendChild(p1);
      }
      if (report.encouragement) {
        const p2 = document.createElement("p");
        p2.innerHTML = "<strong>💪 Motivation:</strong> " + escapeHtml(report.encouragement);
        card.appendChild(p2);
      }
      grid.appendChild(card);
    }

    container.appendChild(grid);
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
      cachedGoalsData = data;
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
      cachedReportData = null;
      if ($("report-content"))
        $("report-content").innerHTML =
          '<div class="loading-msg">AI is analyzing practice performance and generating new report...</div>';
      setTimeout(() => loadReport(1), 2000);
    } catch (e) {
      if ($("report-content"))
        $("report-content").innerHTML =
          '<div class="loading-msg">Failed: ' + escapeHtml(e.message) + "</div>";
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function analyzeSkillsWithAI() {
    const btn = $("skills-ai-btn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "⚡ Analyzing...";
    }
    try {
      const data = await api("/skills/analyze", { method: "POST" });
      skillsLoaded = false;
      await loadSkills();
      if ($("skills-overall")) $("skills-overall").textContent = data.overall_score || "—";
      if ($("hero-score")) {
        $("hero-score").textContent = data.overall_score || "—";
        if ($("hero-ring")) $("hero-ring").style.setProperty("--pct", (data.overall_score || 0) + "%");
      }
      if ($("hero-tier") && data.skill_level) {
        $("hero-tier").textContent = data.skill_level + " (" + data.overall_score + ")";
      }
    } catch (e) {
      alert("AI Analysis: " + e.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "⚡ Analyze with AI";
      }
    }
  }

  // ============================================================
  // One-Tap PDF Report Download
  // ============================================================
  async function downloadFullReportPDF(btn) {
    const originalHtml = btn ? btn.innerHTML : "";
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = "⏳ Generating PDF...";
    }

    try {
      // Ensure all data layers are fetched concurrently if not yet cached
      const fetches = [];

      if (!cachedUserData) {
        fetches.push(
          api("/me")
            .then((u) => { cachedUserData = u; })
            .catch(() => {
              const uEl = $("user");
              cachedUserData = { email: uEl ? uEl.textContent : "Learner" };
            })
        );
      }

      if (!cachedFullData) {
        fetches.push(
          api("/dashboard/full")
            .then((d) => { cachedFullData = d; })
            .catch(async () => {
              const sum = await api("/dashboard/summary").catch(() => null);
              if (sum) {
                cachedFullData = {
                  overall: { ...sum.overall, overall_skill_score: null, streak_days: 0 },
                  problems: sum.problems || [],
                  topics: []
                };
              }
            })
        );
      }

      if (!cachedReportData) {
        fetches.push(
          api("/report")
            .then((r) => { if (r && r.status === "done") cachedReportData = r; })
            .catch(() => {})
        );
      }

      if (!cachedSkillsData) {
        fetches.push(
          api("/skills")
            .then((s) => { cachedSkillsData = s; })
            .catch(() => {})
        );
      }

      if (!cachedGoalsData) {
        fetches.push(
          api("/goals")
            .then((g) => { cachedGoalsData = g; })
            .catch(() => {})
        );
      }

      if (fetches.length) {
        await Promise.allSettled(fetches);
      }

      const user = cachedUserData || { email: ($("user") ? $("user").textContent : "Learner") };
      const full = cachedFullData || {};
      const overall = full.overall || {};
      const problems = (full.problems && full.problems.length) ? full.problems : (allProblemsData || []);
      const topics = (cachedSkillsData && cachedSkillsData.topics) || full.topics || [];
      const report = (cachedReportData && cachedReportData.report) || null;
      const goals = cachedGoalsData || null;

      if (!window.LearnSensePDF || !window.LearnSensePDF.generateAndDownloadReport) {
        throw new Error("LearnSense PDF engine is initializing. Please try again in a moment.");
      }

      window.LearnSensePDF.generateAndDownloadReport({
        user,
        overall,
        fullData: full,
        report,
        topics,
        problems,
        goals
      });

      if (btn) {
        btn.innerHTML = "✅ Downloaded!";
        setTimeout(() => {
          btn.innerHTML = originalHtml;
          btn.disabled = false;
        }, 2200);
      }
    } catch (err) {
      console.error("PDF generation failed:", err);
      alert("Failed to export report PDF: " + err.message);
      if (btn) {
        btn.innerHTML = originalHtml;
        btn.disabled = false;
      }
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
  // Direct Auth & Extension Login (extension-login.html)
  // ============================================================
  function initDirectAuth() {
    const btnSubmit = $("btn-submit");
    const btnReg = $("btn-register");
    const statusMsg = $("status-msg");

    function showMsg(text, isErr) {
      if (!statusMsg) return;
      statusMsg.textContent = text;
      statusMsg.className = "login-msg " + (isErr ? "err" : "ok");
    }

    if (btnSubmit) {
      btnSubmit.onclick = async () => {
        const email = ($("email") ? $("email").value : "").trim();
        const password = ($("password") ? $("password").value : "").trim();
        if (!email || !password) return showMsg("Please enter both email and password.", true);
        btnSubmit.disabled = true;
        btnSubmit.textContent = "Signing In...";
        try {
          const res = await fetch(API + "/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
          });
          const b = await res.json();
          if (!res.ok) throw new Error(b.error || "Login failed");
          localStorage.setItem("learnsense_access_token", b.access_token);
          localStorage.setItem("learnsense_refresh_token", b.refresh_token || "");
          window.postMessage({ type: "LEARNSENSE_DASHBOARD_AUTH" }, "*");
          showMsg("Signed in successfully! Redirecting...", false);
          setTimeout(() => location.replace("index.html"), 500);
        } catch (err) {
          showMsg(err.message, true);
        } finally {
          btnSubmit.disabled = false;
          btnSubmit.textContent = "Sign In";
        }
      };
    }

    if (btnReg) {
      btnReg.onclick = async () => {
        const email = ($("email") ? $("email").value : "").trim();
        const password = ($("password") ? $("password").value : "").trim();
        if (!email || !password) return showMsg("Please enter both email and password.", true);
        btnReg.disabled = true;
        btnReg.textContent = "Registering...";
        try {
          const res = await fetch(API + "/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password, name: email.split("@")[0] }),
          });
          const b = await res.json();
          if (!res.ok) throw new Error(b.error || "Registration failed");
          localStorage.setItem("learnsense_access_token", b.access_token);
          localStorage.setItem("learnsense_refresh_token", b.refresh_token || "");
          window.postMessage({ type: "LEARNSENSE_DASHBOARD_AUTH" }, "*");
          showMsg("Account created! Redirecting...", false);
          setTimeout(() => location.replace("index.html"), 500);
        } catch (err) {
          showMsg(err.message, true);
        } finally {
          btnReg.disabled = false;
          btnReg.textContent = "Create New Account";
        }
      };
    }
  }

  window.handleExtensionLogin = async function () {
    const p = new URLSearchParams(location.search);
    const code = p.get("code");
    if (!code) {
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
      window.postMessage({ type: "LEARNSENSE_DASHBOARD_AUTH" }, "*");
      location.replace("index.html");
    } catch (e) {
      if ($("message")) {
        $("message").textContent = e.message;
        $("message").className = "error";
      }
    }
  };

  // ============================================================
  // Wire up event listeners & boot
  // ============================================================
  if ($("refresh")) $("refresh").onclick = () => {
    cachedFullData = null;
    cachedUserData = null;
    cachedReportData = null;
    cachedSkillsData = null;
    cachedGoalsData = null;
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
      try {
        window.postMessage({ type: "LEARNSENSE_DASHBOARD_LOGOUT" }, "*");
      } catch (e) {}
      location.href = "extension-login.html";
    };

  if ($("save-goal")) $("save-goal").onclick = saveGoal;
  if ($("regen-btn")) $("regen-btn").onclick = regenerateReport;
  if ($("skills-ai-btn")) $("skills-ai-btn").onclick = analyzeSkillsWithAI;

  // One-tap PDF export buttons
  const btnHeaderPDF = $("btn-download-pdf-header");
  const btnHeroPDF = $("btn-download-pdf-hero");
  const btnReportPDF = $("btn-download-pdf-report");

  if (btnHeaderPDF) btnHeaderPDF.onclick = () => downloadFullReportPDF(btnHeaderPDF);
  if (btnHeroPDF) btnHeroPDF.onclick = () => downloadFullReportPDF(btnHeroPDF);
  if (btnReportPDF) btnReportPDF.onclick = () => downloadFullReportPDF(btnReportPDF);

  // Initialize direct auth if on extension-login page
  initDirectAuth();

  // Initialize tabs
  initTabs();
  initProblemSearch();
  initCodeTabs();

  // Boot: only load on dashboard (not on extension-login.html)
  if (
    location.pathname.endsWith("index.html") ||
    location.pathname.endsWith("/dashboard/") ||
    location.pathname.endsWith("/dashboard") ||
    location.pathname.endsWith("/")
  )
    load();
})();
