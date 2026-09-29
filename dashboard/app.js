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
  async function load() {
    if (!token()) {
      location.href = "extension-login.html";
      return;
    }
    try {
      const me = await api("/me");
      $("user").textContent = me.email;
      const data = await api("/dashboard/summary");
      $("solved").textContent = data.overall.solved_problems;
      $("correct").textContent = data.overall.correct;
      $("wrong").textContent = data.overall.wrong;
      $("accuracy").textContent = data.overall.accuracy + "%";
      const body = $("problems");
      body.innerHTML = "";
      data.problems.forEach((p) => {
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
        body.appendChild(tr);
      });
      $("status").textContent = data.problems.length + " problems";
    } catch (e) {
      if (
        e.message.toLowerCase().includes("token") ||
        e.message.toLowerCase().includes("authorization")
      ) {
        localStorage.removeItem("learnsense_access_token");
        location.href = "extension-login.html";
      } else $("status").textContent = e.message;
    }
  }
  async function showProblem(slug) {
    try {
      const d = await api("/problems/" + encodeURIComponent(slug));
      const s = d.submissions[0];
      $("solutionMeta").textContent =
        d.problem.title + " · " + s.language + " · " + fmt(s.submitted_at);
      $("code").textContent = s.code || "(empty code)";
    } catch (e) {
      $("solutionMeta").textContent = e.message;
    }
  }
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
  if ($("refresh")) $("refresh").onclick = load;
  if ($("logout"))
    $("logout").onclick = function () {
      localStorage.removeItem("learnsense_access_token");
      localStorage.removeItem("learnsense_refresh_token");
      location.href = "extension-login.html";
    };
  if (
    location.pathname.endsWith("index.html") ||
    location.pathname.endsWith("/")
  )
    load();
})();
