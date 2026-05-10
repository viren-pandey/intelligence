const API_BASE = window.location.origin;

function getStored() {
  try {
    return JSON.parse(localStorage.getItem('nexus_session') || '{}');
  } catch { return {}; }
}

function setStored(data) {
  localStorage.setItem('nexus_session', JSON.stringify(data));
}

function clearSession() {
  localStorage.removeItem('nexus_session');
}

function isLoggedIn() {
  const s = getStored();
  return !!(s.api_key && s.client_id);
}

async function apiCall(method, path, body, useKey = true) {
  const headers = { 'Content-Type': 'application/json' };
  const s = getStored();
  if (useKey && s.api_key) {
    headers['X-API-Key'] = s.api_key;
  }
  const opts = { method, headers };
  if (body) {
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(API_BASE + path, opts);
  const text = await res.text();
  try {
    return { ok: res.ok, status: res.status, data: JSON.parse(text) };
  } catch {
    return { ok: res.ok, status: res.status, data: text };
  }
}

async function login(clientName, password) {
  const form = new URLSearchParams();
  form.set('client_name', clientName);
  form.set('password', password);
  const res = await fetch(API_BASE + '/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form.toString(),
  });
  const data = await res.json();
  if (res.ok) {
    setStored({ api_key: data.api_key, client_id: data.client_id, client_name: clientName });
  }
  return { ok: res.ok, data };
}

async function checkCredits() {
  return apiCall('GET', '/api/stats');
}

async function getHealth() {
  return apiCall('GET', '/api/health', null, false);
}

async function analyzeProfile(profile, options) {
  const body = {
    request_id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2),
    source: 'dashboard',
    student: profile,
    options: options || { max_results: 10, include_unpaid: false, include_niche: true, freshness_days: 30, mode: 'sync' },
  };
  return apiCall('POST', '/api/analyze', body);
}

async function getJobs(params) {
  const q = params ? '?' + new URLSearchParams(params).toString() : '';
  return apiCall('GET', '/api/jobs' + q);
}

async function registerWebhook(url, events) {
  const form = new URLSearchParams();
  form.set('webhook_url', url);
  form.set('events', events || 'crawl_complete');
  const s = getStored();
  const res = await fetch(API_BASE + '/api/webhook/register', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-API-Key': s.api_key || '',
    },
    body: form.toString(),
  });
  return { ok: res.ok, status: res.status, data: await res.json() };
}

function formatTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toLocaleString();
}

function copyText(text) {
  navigator.clipboard.writeText(text).catch(() => {});
}
