importScripts('config.js');
const API_BASE = self.LEARNSENSE_API_BASE;

function getStorage(keys) {
  return new Promise(resolve => chrome.storage.local.get(keys, resolve));
}

function setStorage(values) {
  return new Promise(resolve => chrome.storage.local.set(values, resolve));
}

function removeStorage(keys) {
  return new Promise(resolve => chrome.storage.local.remove(keys, resolve));
}

async function request(path, options = {}) {
  const stored = await getStorage(['authToken']);
  const headers = Object.assign({'Content-Type': 'application/json'}, options.headers || {});
  if (stored.authToken) headers.Authorization = 'Bearer ' + stored.authToken;

  const response = await fetch(API_BASE + path, {...options, headers});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.error || ('HTTP ' + response.status));
    error.status = response.status;
    throw error;
  }
  return body;
}

async function syncAccepted(entry) {
  const stored = await getStorage(['authToken']);
  if (!stored.authToken) {
    return {synced: false, reason: 'not_logged_in'};
  }

  try {
    const result = await request('/submissions', {
      method: 'POST',
      body: JSON.stringify({
        title: entry.title,
        problemSlug: entry.problemSlug,
        problemUrl: entry.problemUrl,
        verdict: 'Accepted',
        code: entry.code || '',
        lang: entry.lang || 'unknown',
        timestamp: entry.timestamp,
        rightAttempts: entry.rightAttempts,
        wrongAttempts: entry.wrongAttempts,
        totalAttempts: entry.totalAttempts
      })
    });
    return {synced: true, result};
  } catch (error) {
    console.warn('[LearnSense] Accepted submission sync failed:', error.message);
    return {synced: false, reason: error.message};
  }
}

async function openDashboard() {
  const stored = await getStorage(['authToken']);
  if (!stored.authToken) {
    return {ok: false, reason: 'not_logged_in'};
  }

  try {
    const result = await request('/auth/dashboard-code', {method: 'POST'});
    await chrome.tabs.create({url: result.url});
    return {ok: true};
  } catch (error) {
    return {ok: false, reason: error.message};
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      if (message.action === 'syncAccepted') {
        sendResponse(await syncAccepted(message.entry));
        return;
      }
      if (message.action === 'openDashboard') {
        sendResponse(await openDashboard());
        return;
      }
      if (message.action === 'apiRequest') {
        sendResponse({ok: true, data: await request(message.path, message.options || {})});
        return;
      }
      if (message.action === 'saveAuth') {
        await setStorage({authToken: message.token});
        sendResponse({ok: true});
        return;
      }
      if (message.action === 'clearAuth') {
        await removeStorage(['authToken']);
        sendResponse({ok: true});
        return;
      }
      sendResponse({ok: false, reason: 'Unknown action'});
    } catch (error) {
      sendResponse({ok: false, reason: error.message});
    }
  })();
  return true;
});
