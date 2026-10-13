(function () {
  'use strict';
  const API = window.LEARNSENSE_API_BASE;
  const $ = (id) => document.getElementById(id);

  // ── Auth ──────────────────────────────────────────────────
  function token() { return localStorage.getItem('learnsense_access_token') || ''; }
  function refreshTok() { return localStorage.getItem('learnsense_refresh_token') || ''; }

  async function api(path, opts = {}) {
    const headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (token()) headers.Authorization = 'Bearer ' + token();
    let r = await fetch(API + path, { ...opts, headers });
    if (r.status === 401 && path !== '/auth/refresh' && refreshTok()) {
      const rr = await fetch(API + '/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + refreshTok() },
      });
      const rb = await rr.json().catch(() => ({}));
      if (rr.ok && rb.access_token) {
        localStorage.setItem('learnsense_access_token', rb.access_token);
        headers.Authorization = 'Bearer ' + rb.access_token;
        r = await fetch(API + path, { ...opts, headers });
      }
    }
    const b = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(b.error || 'Request failed (' + r.status + ')');
    return b;
  }

  function logout() {
    localStorage.removeItem('learnsense_access_token');
    localStorage.removeItem('learnsense_refresh_token');
    location.href = 'extension-login.html';
  }

  // ── Utilities ─────────────────────────────────────────────
  function fmt(s) {
    return new Date(s).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  }
  function esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
  function pct(n, t) { return t ? Math.round(n / t * 100) : 0; }

  // ── Tab switching ─────────────────────────────────────────
  let activeTab = 'overview';
  const tabLoaded = {};

  function switchTab(name) {
    document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('.tab-content').forEach(s => s.classList.toggle('active', s.id === 'tab-' + name));
    activeTab = name;
    if (!tabLoaded[name]) {
      tabLoaded[name] = true;
      loadTab(name);
    }
  }

  document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => switchTab(b.dataset.tab)));

  // ── Overview ──────────────────────────────────────────────
  let allProblems = [];

  async function loadOverview() {
    try {
      const data = await api('/dashboard/full');
      // Header user
      $('user').textContent = data.user.email;
      // Hero
      const oss = data.overall.overall_skill_score || 0;
      $('hero-score').textContent = oss;
      const ring = document.querySelector('.skill-score-ring');
      if (ring) ring.style.setProperty('--pct', (oss / 100 * 360) + 'deg');
      $('streak-val').textContent = data.overall.streak_days || 0;
      $('solved-val').textContent = data.overall.solved_problems;
      $('accuracy-val').textContent = (data.overall.accuracy || 0) + '%';
      // Stat cards
      $('stat-solved').textContent = data.overall.solved_problems;
      $('stat-correct').textContent = data.overall.correct;
      $('stat-wrong').textContent = data.overall.wrong;
      $('stat-accuracy').textContent = (data.overall.accuracy || 0) + '%';
      // Store problems for search tab
      allProblems = data.problems || [];
      renderProblemsTable('overview-problems', allProblems);
      $('overview-status').textContent = allProblems.length + ' problems';
      // Skills pill on overview
      if (data.topics && data.topics.length) {
        $('skills-overall').textContent = oss;
        renderTopics(data.topics);
        tabLoaded['skills'] = true;
      }
    } catch (e) {
      if (e.message.toLowerCase().includes('token') || e.message.includes('401')) {
        logout();
      } else {
        $('overview-status').textContent = e.message;
      }
    }
  }

  function renderProblemsTable(tbodyId, problems) {
    const tbody = $(tbodyId);
    tbody.innerHTML = '';
    if (!problems.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#6b7a96">No problems yet</td></tr>';
      return;
    }
    problems.forEach(p => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><button class="problem-btn">${esc(p.title)}</button></td>
        <td class="good">${p.correct}</td>
        <td class="bad">${p.wrong}</td>
        <td>${p.attempts}</td>
        <td>${p.accuracy}%</td>
        <td>${fmt(p.last_solved_at)}</td>
      `;
      tr.querySelector('button').onclick = () => showCode(p.slug, p.title);
      tbody.appendChild(tr);
    });
  }

  async function showCode(slug, title) {
    $('solution-meta').textContent = 'Loading...';
    $('code-view').textContent = '';
    try {
      const d = await api('/problems/' + encodeURIComponent(slug));
      const s = d.submissions && d.submissions[0];
      if (!s) {
        $('solution-meta').textContent = title + ' · No code stored';
        $('code-view').textContent = '(no code available)';
        return;
      }
      $('solution-meta').textContent = `${d.problem.title} · ${s.language} · ${fmt(s.submitted_at)}`;
      $('code-view').textContent = s.code || '(empty)';
      // Scroll into view on mobile
      if (window.innerWidth <= 1100) {
        document.getElementById('code-panel').scrollIntoView({ behavior: 'smooth' });
      }
    } catch (e) {
      $('solution-meta').textContent = e.message;
    }
  }

  // ── Skills ────────────────────────────────────────────────
  async function loadSkills() {
    try {
      const data = await api('/skills');
      $('skills-overall').textContent = data.overall_score || 0;
      renderTopics(data.topics || []);
    } catch (e) {
      $('topic-grid').innerHTML = '<div class="error-msg">' + esc(e.message) + '</div>';
    }
  }

  function renderTopics(topics) {
    const grid = $('topic-grid');
    grid.innerHTML = '';
    if (!topics.length) {
      grid.innerHTML = '<div class="loading-msg">No skill data yet. Submit some problems!</div>';
      return;
    }
    topics.forEach(t => {
      const labelClass = 'label-' + (t.label || 'provisional').toLowerCase().replace(/\s/g,'-');
      const confPct = Math.round((t.confidence || 0) * 100);
      const card = document.createElement('div');
      card.className = 'topic-card';
      card.innerHTML = `
        <div class="tc-name">${esc(t.topic)}</div>
        <div class="tc-score">${t.score || 0}</div>
        <span class="tc-label ${labelClass}">${esc(t.label || 'Provisional')}</span>
        <div class="conf-bar">
          <div class="conf-bar-label">Confidence: ${confPct}%</div>
          <div class="conf-track"><div class="conf-fill" style="width:${confPct}%"></div></div>
        </div>
        <div class="tc-problems">${t.problems_seen} problem${t.problems_seen !== 1 ? 's' : ''}</div>
      `;
      grid.appendChild(card);
    });
  }

  // ── AI Report ─────────────────────────────────────────────
  async function loadReport() {
    const container = $('report-content');
    container.innerHTML = '<div class="loading-msg">Loading report...</div>';
    try {
      let data;
      try { data = await api('/report'); } catch(e) {
        if (e.message.includes('202') || e.status === 202) {
          container.innerHTML = '<div class="loading-msg">Report is being generated... refresh in a moment.</div>';
          return;
        }
        throw e;
      }
      if (data.status === 'pending' || data.status === 'generating') {
        container.innerHTML = '<div class="loading-msg">⏳ Report is being generated by AI... please refresh in 30 seconds.</div>';
        return;
      }
      if (data.status === 'done' && data.report) {
        renderReport(data.report, data);
      } else {
        container.innerHTML = '<div class="loading-msg">No report yet. Click Regenerate to create one.</div>';
      }
    } catch (e) {
      container.innerHTML = '<div class="error-msg">' + esc(e.message) + '</div>';
    }
  }

  function renderReport(r, meta) {
    const container = $('report-content');
    const strengths = (r.strengths || []).map(s => `<li>${esc(s)}</li>`).join('');
    const weaknesses = (r.weaknesses || []).map(s => `<li>${esc(s)}</li>`).join('');
    const recs = (r.recommendations || []).map(rec => `
      <div class="rec-item">
        <span class="rec-priority pri-${esc(rec.priority || 'medium')}">${esc(rec.priority || 'medium').toUpperCase()}</span>
        <div class="rec-topic">${esc(rec.topic || '')}</div>
        <div class="rec-reason">${esc(rec.reason || '')}</div>
      </div>
    `).join('');
    const path = (r.learning_path || []).map(t => `<span class="path-tag">${esc(t)}</span>`).join('');
    const patterns = (r.top_patterns || []).map(p => `<span class="path-tag">${esc(p)}</span>`).join('');
    const generatedAt = meta.generated_at ? fmt(meta.generated_at) : 'Unknown';
    const modelName = meta.model || 'AI';

    container.innerHTML = `
      <div class="report-grid">
        <div class="report-card full">
          <h3>📊 Skill Summary</h3>
          <p>${esc(r.skill_summary || '')}</p>
        </div>
        <div class="report-card">
          <h3>✅ Strengths</h3>
          <ul>${strengths || '<li>Keep practicing!</li>'}</ul>
        </div>
        <div class="report-card">
          <h3>⚠️ Areas to Improve</h3>
          <ul>${weaknesses || '<li>Continue building problem diversity</li>'}</ul>
        </div>
        <div class="report-card">
          <h3>🧩 Top Patterns Used</h3>
          <div class="path-list">${patterns || '<span class="path-tag">Analyzing...</span>'}</div>
        </div>
        <div class="weekly-card">
          <h3>🎯 Weekly Target</h3>
          <p>${esc(r.weekly_target || 'Set a goal to get targets')}</p>
        </div>
        <div class="report-card full">
          <h3>🚀 Recommendations</h3>
          ${recs || '<p>No recommendations yet. Solve more problems!</p>'}
        </div>
        <div class="report-card full">
          <h3>📚 Learning Path</h3>
          <div class="path-list">${path || '<span class="path-tag">Not enough data</span>'}</div>
        </div>
        <div class="encouragement-card">
          <p>"${esc(r.encouragement || 'Keep going!')}"</p>
        </div>
      </div>
      <div class="report-footer">
        <span class="muted">Generated by ${esc(modelName)} · ${generatedAt}</span>
      </div>
    `;
    $('report-meta').textContent = 'Last updated: ' + generatedAt;
  }

 const regenBtn = $('regen-btn');

if (regenBtn) {
  regenBtn.addEventListener('click', async () => {
    regenBtn.disabled = true;
    regenBtn.textContent = 'Generating...';

    try {
      await api('/report/regenerate', { method: 'POST' });

      $('report-content').innerHTML =
        '<div class="loading-msg">⏳ AI is generating your report... please wait 30 seconds then refresh.</div>';

      tabLoaded['report'] = false;
    } catch (e) {
      $('report-content').innerHTML =
        '<div class="error-msg">' + esc(e.message) + '</div>';
    } finally {
      regenBtn.disabled = false;
      regenBtn.textContent = 'Regenerate';
    }
  });
}

  // ── Problems tab ──────────────────────────────────────────
  function loadProblems() {
    renderProblemsTable('all-problems', allProblems);
    $('problem-search').addEventListener('input', function() {
      const q = this.value.toLowerCase();
      const filtered = allProblems.filter(p => p.title.toLowerCase().includes(q));
      renderProblemsTable('all-problems', filtered);
    });
  }

  // ── Goals tab ─────────────────────────────────────────────
  async function loadGoals() {
    try {
      const data = await api('/goals');
      if (data.goal) {
        $('goal-type').value = data.goal.type || 'general';
        $('goal-daily').value = data.goal.daily_target_minutes || '';
        $('goal-date').value = data.goal.target_date || '';
        $('goal-notes').value = data.goal.notes || '';
      }
    } catch (e) { /* ignore */ }
  }

  $('save-goal').addEventListener('click', async () => {
    $('save-goal').disabled = true;
    try {
      await api('/goals', {
        method: 'PUT',
        body: JSON.stringify({
          type: $('goal-type').value,
          daily_target_minutes: parseInt($('goal-daily').value) || null,
          target_date: $('goal-date').value || null,
          notes: $('goal-notes').value || null,
        }),
      });
      $('goal-msg').textContent = '✓ Goal saved!';
      $('goal-msg').className = 'good';
    } catch (e) {
      $('goal-msg').textContent = e.message;
      $('goal-msg').className = 'bad';
    } finally {
      $('save-goal').disabled = false;
    }
  });

  // ── Tab router ────────────────────────────────────
  function loadTab(name) {
    if (name === 'overview') loadOverview();
    else if (name === 'skills') loadSkills();
    else if (name === 'report') loadReport();
    else if (name === 'problems') loadProblems();
    else if (name === 'goals') loadGoals();
  }

  // ── Refresh button ────────────────────────────────────────
  $('refresh').addEventListener('click', () => {
    tabLoaded[activeTab] = false;
    loadTab(activeTab);
  });

  // ── Logout ────────────────────────────────────────────────
  $('logout').addEventListener('click', logout);

  // ── Extension login handler (extension-login.html) ────────
  window.handleExtensionLogin = async function () {
    const p = new URLSearchParams(location.search);
    const code = p.get('code');
    if (!code) {
      $('message').textContent = 'Missing sign-in code.';
      $('message').className = 'error';
      return;
    }
    try {
      const r = await fetch(API + '/auth/exchange-dashboard-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      });
      const b = await r.json();
      if (!r.ok) throw new Error(b.error || 'Sign-in failed');
      localStorage.setItem('learnsense_access_token', b.access_token);
      localStorage.setItem('learnsense_refresh_token', b.refresh_token || '');
      location.replace('index.html');
    } catch (e) {
      $('message').textContent = e.message;
      $('message').className = 'error';
    }
  };

  // ── Boot ──────────────────────────────────────────────────
  function boot() {
    if (!token()) {
      location.href = 'extension-login.html';
      return;
    }
    // Load overview by default
    tabLoaded['overview'] = true;
    loadOverview();
  }

  if (location.pathname.endsWith('index.html') || location.pathname.endsWith('/')) {
    boot();
  }
})();
