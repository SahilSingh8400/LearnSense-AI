(function () {
  'use strict';

  var state = {stats: {correct: 0, wrong: 0}, history: [], problemStats: {}, selectedIndex: 0};
  var mode = 'login';

  var authPanel = document.getElementById('authPanel');
  var appPanel = document.getElementById('appPanel');
  var loginTab = document.getElementById('loginTab');
  var signupTab = document.getElementById('signupTab');
  var nameInput = document.getElementById('nameInput');
  var emailInput = document.getElementById('emailInput');
  var passwordInput = document.getElementById('passwordInput');
  var authBtn = document.getElementById('authBtn');
  var authMessage = document.getElementById('authMessage');
  var userEmail = document.getElementById('userEmail');
  var syncStatus = document.getElementById('syncStatus');
  var correctCountEl = document.getElementById('correctCount');
  var wrongCountEl = document.getElementById('wrongCount');
  var accuracyEl = document.getElementById('accuracyValue');
  var historyEl = document.getElementById('history');
  var codeTitleEl = document.getElementById('codeTitle');
  var codeVerdictEl = document.getElementById('codeVerdict');
  var codeTimeEl = document.getElementById('codeTime');
  var codeViewEl = document.getElementById('codeView');
  var problemStatsEl = document.getElementById('problemStats');

  function send(message) {
    return new Promise(function (resolve, reject) {
      chrome.runtime.sendMessage(message, function (response) {
        if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
        resolve(response);
      });
    });
  }

  function escapeHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function formatTime(ts) {
    return new Date(ts).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'});
  }

  function renderStats() {
    var correct = state.stats.correct || 0, wrong = state.stats.wrong || 0, total = correct + wrong;
    correctCountEl.textContent = correct;
    wrongCountEl.textContent = wrong;
    accuracyEl.textContent = (total ? Math.round(correct / total * 100) : 0) + '%';
  }

  function renderProblemStats() {
    var rows = Object.keys(state.problemStats || {}).map(function (key) {
      var p = state.problemStats[key];
      var total = (p.correct || 0) + (p.wrong || 0);
      return {title:p.title || 'Untitled', correct:p.correct || 0, wrong:p.wrong || 0, attempts:total};
    }).sort(function(a,b){return b.attempts-a.attempts;}).slice(0,5);
    problemStatsEl.innerHTML = rows.length ? '' : '<div class="problem-empty">No question statistics yet.</div>';
    rows.forEach(function (p) {
      var row = document.createElement('div'); row.className = 'problem-row';
      row.innerHTML = '<div class="problem-name">' + escapeHtml(p.title) + '</div>' +
        '<div class="problem-result"><span class="p-correct">✓ ' + p.correct + '</span><span class="p-wrong">✗ ' + p.wrong + '</span><span>' + p.attempts + ' attempts</span></div>';
      problemStatsEl.appendChild(row);
    });
  }

  function renderHistory() {
    historyEl.innerHTML = '';
    if (!state.history.length) { historyEl.innerHTML = '<div class="empty">Nothing tracked yet.</div>'; return; }
    state.history.forEach(function (entry, i) {
      var item = document.createElement('button'); item.type='button'; item.className='history-item' + (i===state.selectedIndex?' active':'');
      item.innerHTML = '<span class="dot ' + (entry.verdict === 'Accepted' ? 'ok':'bad') + '"></span><span class="h-title">' + escapeHtml(entry.title || 'Untitled') + '</span>';
      item.addEventListener('click', function(){ state.selectedIndex=i; renderHistory(); renderCode(); });
      historyEl.appendChild(item);
    });
  }

  function renderCode() {
    var entry = state.history[state.selectedIndex];
    if (!entry) {
      codeTitleEl.textContent='No submissions yet'; codeVerdictEl.textContent=''; codeTimeEl.textContent='';
      codeViewEl.innerHTML='<p class="empty-note">Solve a problem on LeetCode and hit Submit.</p>'; return;
    }
    codeTitleEl.textContent=entry.title || 'Untitled'; codeVerdictEl.textContent=entry.verdict; codeVerdictEl.className='verdict ' + (entry.verdict==='Accepted'?'ok':'bad'); codeTimeEl.textContent=formatTime(entry.timestamp);
    codeViewEl.innerHTML=(entry.code || '(no code captured)').split('\n').map(function(line){return '<div class="code-line">'+escapeHtml(line)+'</div>';}).join('');
  }

  function loadLocal() {
    chrome.storage.local.get(['stats','history','problemStats'], function(data){
      state.stats=data.stats || {correct:0,wrong:0}; state.history=data.history || []; state.problemStats=data.problemStats || {};
      if (state.selectedIndex >= state.history.length) state.selectedIndex=0;
      renderStats(); renderProblemStats(); renderHistory(); renderCode();
    });
  }

  async function checkAuth() {
    var data = await new Promise(function(resolve){chrome.storage.local.get(['authToken','user'],resolve);});
    if (!data.authToken) { authPanel.classList.remove('hidden'); appPanel.classList.add('hidden'); return; }
    try {
      var result = await send({action:'apiRequest', path:'/me'});
      if (!result.ok) throw new Error(result.reason || 'Session expired');
      authPanel.classList.add('hidden'); appPanel.classList.remove('hidden');
      userEmail.textContent=result.data.email;
    } catch (e) {
      await send({action:'clearAuth'});
      authPanel.classList.remove('hidden'); appPanel.classList.add('hidden');
    }
  }

  function setMode(next) {
    mode=next;
    var signup=mode==='signup';
    loginTab.classList.toggle('active', !signup); signupTab.classList.toggle('active', signup);
    nameInput.classList.toggle('hidden', !signup); authBtn.textContent=signup?'Create account':'Login';
    authMessage.textContent='';
  }

  async function authenticate() {
    var email=emailInput.value.trim(), password=passwordInput.value, name=nameInput.value.trim();
    if (!email || !password || (mode==='signup' && !name)) { authMessage.textContent='Fill in all required fields.'; return; }
    if (mode==='signup' && password.length < 8) { authMessage.textContent='Password must be at least 8 characters.'; return; }
    authBtn.disabled=true; authMessage.textContent=mode==='signup'?'Creating account...':'Logging in...';
    try {
      var result=await send({action:'apiRequest', path:mode==='signup'?'/auth/register':'/auth/login', options:{method:'POST',body:JSON.stringify({email:email,password:password,name:name})}});
      if (!result.ok) throw new Error(result.reason || 'Authentication failed');
      await send({action:'saveAuth', token:result.data.access_token});
      authMessage.textContent='';
      await checkAuth();
    } catch(e) { authMessage.textContent=e.message; }
    finally { authBtn.disabled=false; }
  }

  loginTab.addEventListener('click', function(){setMode('login');});
  signupTab.addEventListener('click', function(){setMode('signup');});
  authBtn.addEventListener('click', authenticate);
  passwordInput.addEventListener('keydown', function(e){if(e.key==='Enter') authenticate();});

  document.getElementById('logoutBtn').addEventListener('click', async function(){ await send({action:'clearAuth'}); checkAuth(); });
  document.getElementById('dashboardBtn').addEventListener('click', async function(){
    syncStatus.textContent='Opening dashboard...';
    var result=await send({action:'openDashboard'});
    syncStatus.textContent=result.ok?'Dashboard opened.':('Dashboard: '+(result.reason || 'login required'));
  });
  document.getElementById('resetBtn').addEventListener('click', function(){
    if (!confirm('Clear local attempt history? Server data will not be deleted.')) return;
    chrome.storage.local.set({stats:{correct:0,wrong:0},history:[],problemStats:{}},loadLocal);
  });
  document.getElementById('copyBtn').addEventListener('click', function(){
    var entry=state.history[state.selectedIndex]; if(!entry) return;
    navigator.clipboard.writeText(entry.code || '').then(function(){
      var old=document.getElementById('copyBtn').textContent; document.getElementById('copyBtn').textContent='Copied'; setTimeout(function(){document.getElementById('copyBtn').textContent=old;},1000);
    });
  });
  chrome.storage.onChanged.addListener(function(changes,area){if(area==='local'&&(changes.stats||changes.history))loadLocal();});

  loadLocal(); checkAuth();
})();
