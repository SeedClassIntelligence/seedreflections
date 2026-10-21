// SRT-1 Consumer PWA — Service Worker
// Handles: offline caching, background sync, push notifications

const CACHE_NAME = 'srt1-consumer-v1';
const APP_SHELL = [
  '/seed-reflection/mobile.html',
  '/seed-reflection/manifest.json',
  '/seed-reflection/dashboard.html',
  '/seed-reflection/index.html',
  '/seed-reflection/assets/style.css',
  '/js/platform.js',
];

// ── Install: cache app shell ───────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return Promise.allSettled(APP_SHELL.map(url =>
        cache.add(url).catch(() => null) // ignore individual failures
      ));
    })
  );
  self.skipWaiting();
});

// ── Activate: evict stale caches ──────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// ── Fetch: cache-first for shell, network-first for API ───────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Pass through non-GET and cross-origin requests
  if (event.request.method !== 'GET') return;
  if (url.origin !== location.origin) return;

  // API calls: network-first, return offline stub on failure
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request)
        .catch(() => new Response(JSON.stringify({ error: 'offline', offline: true }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' }
        }))
    );
    return;
  }

  // App shell: cache-first, then network, then offline fallback
  event.respondWith(
    caches.match(event.request).then(cached => {
      if (cached) return cached;
      return fetch(event.request).then(response => {
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => {
        // Offline fallback for HTML navigation
        if (event.request.mode === 'navigate') {
          return caches.match('/seed-reflection/mobile.html');
        }
        return new Response('', { status: 503 });
      });
    })
  );
});

// ── Background Sync: flush offline-queued seeds ───────────────────────────
self.addEventListener('sync', event => {
  if (event.tag === 'sync-seeds') {
    event.waitUntil(syncOfflineSeeds());
  }
  if (event.tag === 'sync-imports') {
    event.waitUntil(syncOfflineImports());
  }
});

async function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('srt1-offline', 2);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains('pending_seeds')) {
        db.createObjectStore('pending_seeds', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('pending_imports')) {
        db.createObjectStore('pending_imports', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('seeds')) {
        const store = db.createObjectStore('seeds', { keyPath: 'id' });
        store.createIndex('status', 'status');
        store.createIndex('platform', 'platform');
        store.createIndex('date', 'date');
      }
    };
    req.onsuccess = e => resolve(e.target.result);
    req.onerror = () => reject(req.error);
  });
}

async function getAllFromStore(db, storeName) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readonly');
    const req = tx.objectStore(storeName).getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

async function deleteFromStore(db, storeName, id) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite');
    const req = tx.objectStore(storeName).delete(id);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

async function syncOfflineSeeds() {
  let db;
  try { db = await openDB(); } catch { return; }
  const pending = await getAllFromStore(db, 'pending_seeds');
  for (const seed of pending) {
    try {
      const resp = await fetch('/api/v1/seeds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Offline-Sync': '1' },
        body: JSON.stringify(seed),
      });
      if (resp.ok) await deleteFromStore(db, 'pending_seeds', seed.id);
    } catch { /* retry next sync */ }
  }
  // Notify open clients
  notifyClients({ type: 'SYNC_COMPLETE', count: pending.length });
}

async function syncOfflineImports() {
  let db;
  try { db = await openDB(); } catch { return; }
  const pending = await getAllFromStore(db, 'pending_imports');
  for (const item of pending) {
    try {
      const resp = await fetch('/api/v1/files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Offline-Sync': '1' },
        body: JSON.stringify(item),
      });
      if (resp.ok) await deleteFromStore(db, 'pending_imports', item.id);
    } catch { /* retry next sync */ }
  }
}

function notifyClients(message) {
  self.clients.matchAll({ type: 'window' }).then(clients => {
    clients.forEach(client => client.postMessage(message));
  });
}

// ── Push notifications (future) ───────────────────────────────────────────
self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || 'Seed Reflection';
  const options = {
    body: data.body || 'You have updates in your idea garden.',
    icon: '/seed-reflection/manifest.json',
    badge: '/seed-reflection/manifest.json',
    tag: data.tag || 'srt1',
    data: { url: data.url || '/seed-reflection/mobile.html' },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data.url || '/seed-reflection/mobile.html')
  );
});
