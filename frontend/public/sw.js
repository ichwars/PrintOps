// PrintOps Service Worker
const CACHE_NAME = 'printops-v4';
const STATIC_CACHE = 'printops-static-v3';
const HASHED_ASSET = /^\/assets\/[^/]+-[A-Za-z0-9_-]{8}\.[A-Za-z0-9]+$/;
const ENTRY_SCRIPT = /\/assets\/index-[A-Za-z0-9_-]{8}\.js/;
const ENTRY_CACHE_KEY = '/__printops_active_build__';

async function prunePreviousBuild(response) {
  const entry = (await response.text()).match(ENTRY_SCRIPT)?.[0];
  if (!entry) return;
  const cache = await caches.open(CACHE_NAME);
  const previous = await cache.match(ENTRY_CACHE_KEY);
  const previousEntry = previous && await previous.text();
  if (previousEntry === entry) return;
  const keys = previousEntry ? await cache.keys() : [];
  await cache.put(ENTRY_CACHE_KEY, new Response(entry));
  await Promise.all(keys.filter((key) => {
    const path = new URL(key.url).pathname;
    return HASHED_ASSET.test(path) && path !== entry;
  }).map((key) => cache.delete(key)));
}

function serveHashedAsset(event) {
  const { request } = event;
  const load = caches.match(request).then(async (cached) => {
    if (cached) return { response: cached, fromNetwork: false };
    return { response: await fetch(request), fromNetwork: true };
  });
  event.waitUntil(load.then(async ({ response, fromNetwork }) => {
    const contentType = response.headers.get('content-type') || '';
    if (fromNetwork && response.status === 200 && !contentType.includes('text/html')) {
      const copy = response.clone();
      const cache = await caches.open(CACHE_NAME);
      await cache.put(request, copy);
    }
  }).catch(() => {}));
  event.respondWith(load.then(({ response }) => response));
}

// Static assets to cache on install
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/img/printops_logo.svg',
  '/img/printops_icon.png',
  '/img/favicon-16x16.png',
  '/img/favicon-32x32.png',
  '/img/favicon.png',
  '/img/apple-touch-icon.png',
  '/img/android-chrome-192x192.png',
  '/img/android-chrome-512x512.png',
  // Self-hosted Inter font (#1460) - cached so the UI renders offline.
  '/fonts/inter-latin.woff2',
  '/fonts/inter-latin-ext.woff2',
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker...');
  event.waitUntil(
    caches.open(STATIC_CACHE).then(async (cache) => {
      console.log('[SW] Caching static assets');
      await cache.addAll(STATIC_ASSETS);

      try {
        const manifestResponse = await fetch('/locale-assets.json', { cache: 'no-store' });
        if (!manifestResponse.ok) return;

        const localeAssets = await manifestResponse.clone().json();
        if (!Array.isArray(localeAssets) || !localeAssets.every((asset) => typeof asset === 'string')) return;

        await cache.put('/locale-assets.json', manifestResponse);
        await cache.addAll(localeAssets);
      } catch (error) {
        console.warn('[SW] Locale assets could not be precached:', error);
      }
    })
  );
  // Activate immediately
  self.skipWaiting();
});

// Activate event - clean up old caches and claim existing clients.
//
// The forced reload that picks up a new bundle on already-open clients (the
// kiosk deploy-pickup scenario) lives in sw-register.js via a
// `controllerchange` listener, gated on whether the page already had a SW
// controller at load time. That gate distinguishes first-install (where a
// reload would race the in-flight React mount — observed on every fresh
// *.demo.github.com/ichwars/PrintOps subdomain, and in Firefox the activate's waitUntil
// hung on `client.navigate` until the document load was aborted with a
// Corrupted-Content error) from upgrade-on-existing-client (where the reload
// is wanted).
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker...');
  event.waitUntil(
    (async () => {
      const cacheNames = await caches.keys();
      await Promise.all(
        cacheNames
          .filter((name) => name.startsWith('printops-') && name !== CACHE_NAME && name !== STATIC_CACHE)
          .map((name) => {
            console.log('[SW] Deleting old cache:', name);
            return caches.delete(name);
          }),
      );
      await self.clients.claim();
    })(),
  );
});

// Fetch event - network-first for API, cache-first for static
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Skip cross-origin requests - let the browser handle them directly.
  // Without this the catch-all HTML branch below would answer a failed
  // cross-origin request with our cached index.html, so e.g. a blocked
  // Google Fonts request came back as text/html (#1460).
  if (url.origin !== self.location.origin) {
    return;
  }

  // Skip WebSocket connections
  if (url.protocol === 'ws:' || url.protocol === 'wss:') {
    return;
  }

  if (url.pathname === '/health' || request.headers.has('range')) {
    return;
  }

  if (HASHED_ASSET.test(url.pathname)) {
    serveHashedAsset(event);
    return;
  }

  // Skip camera stream/snapshot requests - Safari has issues with streaming through SW
  if (url.pathname.includes('/camera/stream') || url.pathname.includes('/camera/snapshot')) {
    return;
  }

  // API requests - network first, no cache (real-time data is critical)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request).catch(() => {
        // Return offline response for API failures
        return new Response(
          JSON.stringify({ error: 'offline', message: 'You are currently offline' }),
          {
            status: 503,
            headers: { 'Content-Type': 'application/json' },
          }
        );
      })
    );
    return;
  }

  // Static assets - cache first, then network
  if (
    url.pathname.startsWith('/img/') ||
    url.pathname.startsWith('/icons/') ||
    url.pathname.startsWith('/fonts/') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.jpg') ||
    url.pathname.endsWith('.svg') ||
    url.pathname.endsWith('.ico') ||
    url.pathname.endsWith('.woff2')
  ) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) {
          return cached;
        }
        return fetch(request).then((response) => {
          // Cache successful responses
          if (response.ok) {
            const clone = response.clone();
            caches.open(STATIC_CACHE).then((cache) => {
              cache.put(request, clone);
            });
          }
          return response;
        });
      })
    );
    return;
  }

  // Unversioned assets must revalidate against the network.
  if (
    url.pathname.startsWith('/assets/') ||
    url.pathname.endsWith('.js') ||
    url.pathname.endsWith('.css')
  ) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, clone);
            });
          }
          return response;
        })
        .catch(() => {
          return caches.match(request);
        })
    );
    return;
  }

  // HTML pages revalidate on every navigation and announce the current build.
  const navigation = fetch(request);
  event.waitUntil(navigation.then(async (response) => {
    if (!response.ok) return;
    const clone = response.clone();
    const pruning = request.mode === 'navigate' && response.headers.get('content-type')?.includes('text/html')
      ? prunePreviousBuild(response.clone())
      : undefined;
    const cache = await caches.open(CACHE_NAME);
    await Promise.all([cache.put(request, clone), pruning]);
  }).catch(() => {}));
  event.respondWith(
    navigation
      .catch(() => {
        return caches.match(request).then((cached) => {
          if (cached) {
            return cached;
          }
          // Return cached index for SPA navigation
          return caches.match('/');
        });
      })
  );
});

// Handle push notifications (for future use)
self.addEventListener('push', (event) => {
  if (!event.data) return;

  const data = event.data.json();
  const options = {
    body: data.body || 'New notification from PrintOps',
    icon: '/img/android-chrome-192x192.png',
    badge: '/img/favicon-32x32.png',
    vibrate: [100, 50, 100],
    data: {
      url: data.url || '/',
    },
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'PrintOps', options)
  );
});

// Handle notification clicks
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const url = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      // Check if there's already a window open
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      // Open a new window if none exists
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});
