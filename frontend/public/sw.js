/* ═══════════════════════════════════════════════════════
   NOC Sentinel v3 — Service Worker (PWA)
   Offline caching strategy: Cache First for static assets,
   Network First for API calls (fail gracefully).
═══════════════════════════════════════════════════════ */

const CACHE_NAME = "noc-sentinel-v3-v2";

// Static assets to cache on install
const PRECACHE_ASSETS = [
  "/",
  "/index.html",
];

// ── Install: precache static shell ──
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch(() => {
        // Don't fail install if precache has issues
      });
    })
  );
  self.skipWaiting();
});

// ── Activate: clean up old caches ──
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch: Network First for API, Cache First for static ──
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET and cross-origin requests
  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  // API calls: Network First — try network, fail silently without cache
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(request).catch(() => {
        return new Response(
          JSON.stringify({ error: "Offline — data tidak tersedia" }),
          { headers: { "Content-Type": "application/json" }, status: 503 }
        );
      })
    );
    return;
  }

  // Static assets: Cache First for JS/CSS/images
  if (
    url.pathname.match(/\.(js|css|png|jpg|svg|ico|woff2?|ttf)$/i)
  ) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // HTML: Network First, fallback to cached index.html (SPA routing)
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((c) => c.put(request, clone));
        }
        return response;
      })
      .catch(() =>
        caches.match("/index.html").then((cached) => {
          if (cached) return cached;
          return new Response(
            "<html><body><p style='font-family:sans-serif;text-align:center;padding:40px'>NOC Sentinel - Offline mode. Check your connection.</p></body></html>",
            { headers: { "Content-Type": "text/html" } }
          );
        })
      )
  );
});

// ── Push Notifications ──────────────────────────────────
self.addEventListener("push", (event) => {
  if (!event.data) return;
  let data;
  try {
    data = event.data.json();
  } catch {
    data = { title: "NOC Sentinel", body: event.data.text() };
  }

  const options = {
    body: data.body || "",
    tag: data.tag || "noc-default",
    icon: "/favicon.ico",
    badge: "/favicon.ico",
    vibrate: [200, 100, 200],
    data: { url: data.url || "/" },
    actions: [
      { action: "open", title: "Buka Dashboard" },
      { action: "dismiss", title: "Tutup" },
    ],
    requireInteraction: data.urgent === true,
  };

  event.waitUntil(
    self.registration.showNotification(data.title || "NOC Sentinel", options)
  );
});

// ── Notification click handler ──
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  if (event.action === "dismiss") return;
  const targetUrl = event.notification.data?.url || "/";
  event.waitUntil(
    clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          if (client.url.includes(self.location.origin)) {
            client.focus();
            client.navigate(targetUrl);
            return;
          }
        }
        return clients.openWindow(targetUrl);
      })
  );
});
