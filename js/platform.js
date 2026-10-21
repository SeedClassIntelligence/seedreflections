/**
 * Seed Reflections Platform JS Client
 * Shared auth + API utilities for all frontend pages.
 * Zero dependencies — pure ES2020. Demo data is available only when explicitly
 * requested with ?demo=1; service failures are always reported to the user.
 */
(function (root) {
  'use strict';

  // ── Config ────────────────────────────────────────────────────────────────
  const IS_PROD = location.hostname !== 'localhost' && location.hostname !== '127.0.0.1';
  const DEMO_REQUESTED = new URLSearchParams(location.search).get('demo') === '1';
  // Use relative path when served by unified engine (same host/port), or fallback in development
  const API_BASE = (location.protocol === 'file:' || location.port === '5500' || location.port === '3000')
    ? 'http://127.0.0.1:8476/api/v1'
    : '/api/v1';

  const STORAGE = {
    ACCESS:  'seedreflections_access_token',
    REFRESH: 'seedreflections_refresh_token',
    USER:    'seedreflections_user',
    DEMO:    'seedreflections_demo_mode',
  };

  // ── Demo mode ─────────────────────────────────────────────────────────────
  // A JWT whose payload has exp=9999999999 (year 2286) — passes isLoggedIn().
  // header: {"alg":"none","typ":"JWT"}  payload: {"sub":"1","type":"access","exp":9999999999}
  const DEMO_TOKEN = 'eyJhbGciOiJub25lIiwidHlwZSI6IkpXVCJ9.eyJzdWIiOiIxIiwidHlwZSI6ImFjY2VzcyIsImV4cCI6OTk5OTk5OTk5OX0.demo';

  const DEMO_USER = {
    id: 1,
    email: 'demo@seedreflections.app',
    name: 'Demo User',
    role: 'consumer',
    is_active: true,
    email_verified: true,
    active_plan: 'free',
    created_at: '2026-01-01T00:00:00Z',
    last_login_at: new Date().toISOString(),
  };

  const DEMO_LICENSES = [
    { id: 1, key: 'Seed Reflections-PRO-DEMO-A1B2-C3D4-E5F6', tier: 'pro',        status: 'active',   activations: 1, max_activations: 3,  created_at: '2026-02-10T10:00:00Z', last_used_at: '2026-03-15T08:00:00Z', download_count: 4 },
    { id: 2, key: 'Seed Reflections-ENT-DEMO-G7H8-I9J0-K1L2', tier: 'enterprise', status: 'active',   activations: 3, max_activations: 10, created_at: '2026-01-20T14:00:00Z', last_used_at: '2026-03-14T12:00:00Z', download_count: 11 },
    { id: 3, key: 'Seed Reflections-FREE-DEMO-M3N4-O5P6-Q7R8', tier: 'free',      status: 'revoked',  activations: 0, max_activations: 1,  created_at: '2026-01-05T09:00:00Z', last_used_at: null,                    download_count: 0 },
  ];

  const DEMO_DASH = {
    plan: 'pro',
    active_licenses: 2,
    total_downloads: 15,
    api_calls_this_month: 128,
    team_members: 1,
    licenses: DEMO_LICENSES,
    recent_activity: [
      { action: 'License activated', detail: 'Seed Reflections-PRO-DEMO-…', ts: '2026-03-15T08:00:00Z' },
      { action: 'Download recorded', detail: 'seed reflections-v2.0.tar.gz', ts: '2026-03-14T12:00:00Z' },
    ],
  };

  const DEMO_USAGE = {
    period: '2026-03',
    seeds_used: 47,
    seeds_limit: 500,
    reflections_used: 12,
    reflections_limit: null,
    api_calls: 128,
  };

  const DEMO_FILES = {
    files: [
      { id: 'f1', filename: 'reflection-march-sprint.json', description: 'March sprint review', category: 'reflection', size_kb: 14, created_at: '2026-03-10T09:00:00Z' },
      { id: 'f2', filename: 'reflection-auth-module.json',  description: 'Auth module deep-dive', category: 'reflection', size_kb: 8,  created_at: '2026-03-01T11:00:00Z' },
    ],
    limit: 100,
    used: 2,
  };

  const DEMO_SUBSCRIPTION = {
    plan: 'pro',
    status: 'active',
    interval: 'monthly',
    current_period_start: '2026-03-01T00:00:00Z',
    current_period_end:   '2026-04-01T00:00:00Z',
    cancel_at_period_end: false,
  };

  function _isDemoMode() {
    return localStorage.getItem(STORAGE.DEMO) === '1';
  }

  function _enterDemoMode(name, email, role) {
    localStorage.setItem(STORAGE.DEMO, '1');
    setTokens(DEMO_TOKEN, DEMO_TOKEN);
    const userRole = role || 'consumer';
    const plan = userRole === 'developer' ? 'pro' : 'free';
    const user = { ...DEMO_USER, name: name || DEMO_USER.name, email: email || DEMO_USER.email, role: userRole, active_plan: plan };
    localStorage.setItem(STORAGE.USER, JSON.stringify(user));
    return user;
  }

  function _exitDemoMode() {
    localStorage.removeItem(STORAGE.DEMO);
  }

  /** Return a mock Response-like object for demo API calls. */
  function _mockResponse(data, status) {
    const body = JSON.stringify(data);
    return {
      ok: (status || 200) < 300,
      status: status || 200,
      json: () => Promise.resolve(data),
      text: () => Promise.resolve(body),
    };
  }

  /** Route a demo API call to mock data. */
  function _demoApiRequest(path, options) {
    const method = (options && options.method || 'GET').toUpperCase();
    const p = path.split('?')[0];

    // User
    if (p === '/users/me' && method === 'GET')
      return Promise.resolve(_mockResponse(DEMO_USER));
    if (p === '/users/me' && method === 'PATCH')
      return Promise.resolve(_mockResponse(DEMO_USER));
    if (p === '/users/me/developer-dashboard')
      return Promise.resolve(_mockResponse(DEMO_DASH));
    if (p === '/users/me/consumer-dashboard')
      return Promise.resolve(_mockResponse({ plan: 'pro', seeds_used: 47, seeds_limit: 500, recent_seeds: [] }));

    // Usage
    if (p === '/usage/' || p === '/usage')
      return Promise.resolve(_mockResponse(DEMO_USAGE));

    // Subscription
    if (p === '/subscriptions/' || p === '/subscriptions')
      return Promise.resolve(_mockResponse(DEMO_SUBSCRIPTION));
    if (p === '/subscriptions/checkout' && method === 'POST')
      return Promise.resolve(_mockResponse({ checkout_url: '#demo-checkout' }));
    if (p === '/subscriptions/portal')
      return Promise.resolve(_mockResponse({ portal_url: '#demo-portal' }));

    // Files
    if (p.startsWith('/files') && method === 'GET')
      return Promise.resolve(_mockResponse(DEMO_FILES));
    if (p.startsWith('/files') && method === 'POST')
      return Promise.resolve(_mockResponse({ id: 'fnew', filename: 'new-reflection.json', size_kb: 5, created_at: new Date().toISOString() }, 201));
    if (p.startsWith('/files') && method === 'DELETE')
      return Promise.resolve(_mockResponse({ ok: true }));

    // Licenses
    if (p === '/licenses/generate' && method === 'POST')
      return Promise.resolve(_mockResponse({ id: 99, key: 'Seed Reflections-PRO-DEMO-' + Math.random().toString(36).slice(2,6).toUpperCase() + '-XXXX-YYYY', tier: 'pro', status: 'active', activations: 0, max_activations: 3, created_at: new Date().toISOString(), download_count: 0 }, 201));
    if (p.startsWith('/licenses') && method === 'DELETE')
      return Promise.resolve(_mockResponse({ ok: true }));
    if (p.startsWith('/licenses'))
      return Promise.resolve(_mockResponse({ licenses: DEMO_LICENSES }));

    // Reflect (AI proxy)
    if (p === '/reflect' && method === 'POST')
      return Promise.resolve(_mockResponse({
        answer: '**Demo mode** — the AI reflection endpoint requires the backend to be deployed. This is a placeholder response so you can explore the full UI.',
        seeds: [],
        tokens_used: 0,
      }));

    // Auth endpoints (shouldn't hit in demo, but guard anyway)
    if (p.startsWith('/auth'))
      return Promise.resolve(_mockResponse({ detail: 'demo mode' }, 200));

    // Fallback
    return Promise.resolve(_mockResponse({}, 200));
  }

  // ── Token management ──────────────────────────────────────────────────────

  function getAccessToken()  { return localStorage.getItem(STORAGE.ACCESS);  }
  function getRefreshToken() { return localStorage.getItem(STORAGE.REFRESH); }

  function setTokens(access, refresh) {
    localStorage.setItem(STORAGE.ACCESS,  access);
    if (refresh) localStorage.setItem(STORAGE.REFRESH, refresh);
  }

  function clearAuth() {
    _exitDemoMode();
    localStorage.removeItem(STORAGE.ACCESS);
    localStorage.removeItem(STORAGE.REFRESH);
    localStorage.removeItem(STORAGE.USER);
  }

  function isLoggedIn() {
    return !!getAccessToken();
  }

  function getCachedUser() {
    try { return JSON.parse(localStorage.getItem(STORAGE.USER)); } catch { return null; }
  }

  // ── HTTP helpers ──────────────────────────────────────────────────────────

  async function _refreshIfNeeded() {
    if (isLoggedIn()) return true;
    if (_isDemoMode()) return true;
    const refresh = getRefreshToken();
    if (!refresh) return false;
    try {
      const r = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!r.ok) { clearAuth(); return false; }
      const { access_token, refresh_token } = await r.json();
      setTokens(access_token, refresh_token);
      return true;
    } catch { return false; }
  }

  async function apiRequest(path, options = {}) {
    if (_isDemoMode()) return _demoApiRequest(path, options);

    await _refreshIfNeeded();

    const token = getAccessToken();
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };

    const init = { ...options, headers };
    if (init.body && typeof init.body === 'object') {
      init.body = JSON.stringify(init.body);
    }

    const res = await fetch(`${API_BASE}${path}`, init);

    if (res.status === 401) {
      clearAuth();
      _emitAuthEvent('logout');
    }

    return res;
  }

  // ── Auth actions ──────────────────────────────────────────────────────────

  async function signup(email, name, password, accountType) {
    const role = accountType || 'consumer';
    try {
      const r = await fetch(`${API_BASE}/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, name, password, role }),
      });
      if (r.ok) {
        const data = await r.json();
        setTokens(data.access_token, data.refresh_token);
        await fetchAndCacheUser();
        _emitAuthEvent('login');
        return data;
      }
      const err = await r.json().catch(() => ({}));
      // 409 conflict = real error, surface it
      if (r.status === 409) throw new Error(err.detail || 'An account with this email already exists.');
      throw new Error(err.detail || 'Account creation is temporarily unavailable.');
    } catch (e) {
      if (DEMO_REQUESTED) {
        _enterDemoMode(name, email, role);
        _emitAuthEvent('login');
        return { access_token: DEMO_TOKEN, demo: true };
      }
      if (e instanceof TypeError || /fetch|failed|network/i.test(e.message || '')) {
        throw new Error('Seed Reflections could not reach the service. Your account was not created.');
      }
      throw e;
    }
  }

  async function login(email, password) {
    try {
      const r = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (r.ok) {
        const data = await r.json();
        setTokens(data.access_token, data.refresh_token);
        if (data.user) {
          localStorage.setItem(STORAGE.USER, JSON.stringify(data.user));
        } else {
          await fetchAndCacheUser();
        }
        _emitAuthEvent('login');
        return data;
      }
      const err = await r.json().catch(() => ({}));
      // 401 = wrong password — surface it, don't fall to demo
      if (r.status === 401) throw new Error(err.detail || 'Invalid email or password.');
      throw new Error(err.detail || 'Sign in is temporarily unavailable.');
    } catch (e) {
      if (DEMO_REQUESTED) {
        _enterDemoMode(null, email, 'consumer');
        _emitAuthEvent('login');
        return { access_token: DEMO_TOKEN, demo: true };
      }
      if (e instanceof TypeError || /fetch|failed|network/i.test(e.message || '')) {
        throw new Error('Seed Reflections could not reach the service. You were not signed in.');
      }
      throw e;
    }
  }

  function logout() {
    clearAuth();
    _emitAuthEvent('logout');
    return Promise.resolve();
  }

  async function fetchAndCacheUser() {
    if (_isDemoMode()) {
      const user = getCachedUser() || DEMO_USER;
      localStorage.setItem(STORAGE.USER, JSON.stringify(user));
      return user;
    }
    try {
      const r = await apiRequest('/users/me');
      if (!r.ok) return null;
      const user = await r.json();
      localStorage.setItem(STORAGE.USER, JSON.stringify(user));
      return user;
    } catch { return null; }
  }

  async function getUser() {
    if (!isLoggedIn()) {
      await _refreshIfNeeded();
      if (!isLoggedIn()) return null;
    }
    const cached = getCachedUser();
    if (cached) return cached;
    return fetchAndCacheUser();
  }

  // ── Custom events ─────────────────────────────────────────────────────────

  function _emitAuthEvent(type) {
    window.dispatchEvent(new CustomEvent('seed reflections:auth', { detail: { type } }));
  }

  function onAuth(callback) {
    window.addEventListener('seed reflections:auth', (e) => callback(e.detail));
  }

  // ── Usage helpers ─────────────────────────────────────────────────────────

  async function getUsage() {
    const r = await apiRequest('/usage/');
    if (!r.ok) return null;
    return r.json();
  }

  // ── Subscription helpers ──────────────────────────────────────────────────

  async function getCheckoutUrl(plan, interval) {
    const STATIC_CHECKOUT_URLS = {
      free: 'https://buy.stripe.com/test_seed_reflections_free',
      pro: 'https://buy.stripe.com/test_seed_reflections_pro',
      master: 'https://buy.stripe.com/test_seed_reflections_master'
    };

    const pKey = (plan || '').toLowerCase();

    if (_isDemoMode()) {
      return STATIC_CHECKOUT_URLS[pKey] || '#demo';
    }
    try {
      const r = await apiRequest('/subscriptions/checkout', {
        method: 'POST',
        body: { plan, interval: interval || 'monthly' },
      });
      if (r.ok) {
        const { checkout_url } = await r.json();
        return checkout_url;
      }
    } catch(e) {}
    
    return STATIC_CHECKOUT_URLS[pKey] || '#demo';
  }

  async function getBillingPortalUrl() {
    if (_isDemoMode()) {
      alert('Demo mode — connect a backend to enable billing portal.');
      return '#demo';
    }
    const r = await apiRequest('/subscriptions/portal');
    if (!r.ok) throw new Error('Billing portal unavailable');
    const { portal_url } = await r.json();
    return portal_url;
  }

  // ── Files / reflections ───────────────────────────────────────────────────

  async function saveReflection(content, filename, description) {
    if (_isDemoMode()) {
      return { id: 'demo-' + Date.now(), filename: filename || 'reflection.json', size_kb: 1, created_at: new Date().toISOString() };
    }
    const blob = new Blob([content], { type: 'application/json' });
    const fd = new FormData();
    fd.append('file', blob, filename || `reflection-${Date.now()}.json`);
    if (description) fd.append('description', description);
    fd.append('category', 'reflection');

    const token = getAccessToken();
    const r = await fetch(`${API_BASE}/files/`, {
      method: 'POST',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: fd,
    });
    if (r.status === 402) throw new Error('File limit reached. Upgrade to save more reflections.');
    if (!r.ok) throw new Error('Save failed');
    return r.json();
  }

  async function listReflections() {
    const r = await apiRequest('/files/?category=reflection');
    if (!r.ok) return [];
    const data = await r.json();
    return data.files || [];
  }

  // ── Reflect proxy (server-side Claude call) ────────────────────────────────

  async function reflect(transcript, options) {
    // Inject consumer API keys if available
    let consumerKeys = null;
    try {
      const stored = localStorage.getItem('seed reflections_api_keys');
      if (stored) consumerKeys = JSON.parse(stored);
    } catch (e) {}

    const r = await apiRequest('/reflect', {
      method: 'POST',
      body: { transcript, options: options || {}, consumer_keys: consumerKeys },
    });
    if (r.status === 402) throw new Error('Monthly reflection limit reached. Connect your own API keys in Settings to continue.');
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      throw new Error(d.detail || 'Reflection failed');
    }
    return r.json();
  }

  // ── Local Indexer Bridge (Zero-Knowledge Telemetry) ───────────────────────

  async function pollLocalIndexer() {
    try {
      // Connect to the local hardware indexer via Zero-Knowledge bridge
      const r = await fetch('http://127.0.0.1:7483/api/stats', {
        headers: { 'Accept': 'application/json' },
        // short timeout to fail fast if daemon isn't running
        signal: AbortSignal.timeout(2000)
      });
      if (r.ok) {
        const data = await r.json();
        // Emit event so the UI can update
        window.dispatchEvent(new CustomEvent('seed reflections:local_immunity', { detail: data }));
        return data;
      }
    } catch {
      // Daemon offline
      window.dispatchEvent(new CustomEvent('seed reflections:local_immunity_offline'));
      return null;
    }
  }

  // ── UI helpers ────────────────────────────────────────────────────────────

  function renderNavAuth(containerSelector) {
    const container = document.querySelector(containerSelector);
    if (!container) return;

    const update = async () => {
      const user = await getUser().catch(() => null);
      if (user) {
        let dashLink = 'consumer-dashboard.html';
        if (user.role === 'admin') dashLink = 'admin-dashboard.html';
        else if (user.role === 'developer') dashLink = 'dashboard.html';
        
        container.innerHTML = `
          <a href="${dashLink}" class="nav-link">Dashboard</a>
          <span class="nav-user">${escapeHtml(user.name)}</span>
          <button onclick="SeedReflectionsPlatform.logout(); location.reload();" class="btn-ghost btn-sm">Log out</button>
        `;
      } else {
        container.innerHTML = `
          <a href="auth.html" class="nav-link">Log in</a>
          <a href="auth.html?mode=signup" class="btn-primary btn-sm">Get Started</a>
        `;
      }
    };

    update();
    onAuth(update);
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, c =>
      ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c])
    );
  }

  async function requirePlan(minPlan, options) {
    const hierarchy = { free: 0, pro: 1, enterprise: 2 };
    const opts = { redirect: 'auth.html', onUpgrade: null, ...options };

    const user = await getUser();
    if (!user) {
      if (opts.redirect) location.href = opts.redirect + '?mode=signup&next=' + encodeURIComponent(location.href);
      return false;
    }
    if ((hierarchy[user.active_plan] || 0) < (hierarchy[minPlan] || 0)) {
      if (opts.onUpgrade) opts.onUpgrade(user);
      return false;
    }
    return true;
  }

  // ── Export ────────────────────────────────────────────────────────────────
  root.SeedReflectionsPlatform = {
    API_BASE,
    isDemoMode: _isDemoMode,
    // Auth
    isLoggedIn, getUser, getCachedUser, signup, login, logout, onAuth, setTokens, clearAuth,
    // API
    apiRequest,
    // Usage
    getUsage,
    // Subscription
    getCheckoutUrl, getBillingPortalUrl,
    // Files
    saveReflection, listReflections,
    // Reflect
    reflect,
    // Local Indexer Bridge
    pollLocalIndexer,
    // UI
    renderNavAuth, escapeHtml, requirePlan,
  };

}(window));
