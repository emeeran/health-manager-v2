// Service worker for the Family Health Manager v2 PWA.
//
// IMPORTANT: API responses (/api/*) are deliberately NEVER cached. This is a
// health-records app — serving stale lab results, medication lists, or AI
// insights would be actively harmful. Only the static app shell (HTML/JS/CSS)
// is cached, so the UI loads fast and survives a flaky network while every
// data request always hits the server.
const CACHE_NAME = "fhm-v2-shell-v1";
const PRECACHE_URLS = ["/", "/index.html"];

// Install — precache the app shell. We do NOT call skipWaiting() here: the
// page prompts the user ("Update available") and sends { type:
// "SKIP_WAITING" } when they accept, so an in-flight action isn't disrupted
// by the app swapping to a new version mid-session.
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)),
  );
});

// Activate — evict ALL caches that aren't the current version and take
// control of any open clients.
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

// Allow the page to activate a waiting update on demand (after the user
// accepts the "Update available" toast).
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only handle same-origin GETs.
  if (request.method !== "GET") return;
  if (!request.url.startsWith(self.location.origin)) return;

  // API requests: never intercept — always go to the network.
  if (request.url.includes("/api/")) return;

  // Navigation: network-first, fall back to the cached app shell offline.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        caches
          .match(request)
          .then((r) => r || caches.match("/") || caches.match("/index.html")),
      ),
    );
    return;
  }

  // Static assets: cache-first (Vite emits content-hashed /assets/* URLs, so
  // a cached hit is always the correct version). Never cache an HTML fallback
  // as JS/CSS — that happens when a hashed chunk is gone after a deploy;
  // serve a 404 so the app can recover via a reload rather than executing
  // HTML as a script.
  if (request.url.match(/\.(js|css|png|jpg|jpeg|gif|svg|ico|woff2?|map)$/)) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            const contentType = response.headers.get("content-type") || "";
            if (
              request.url.match(/\.(js|css)$/) &&
              contentType.includes("text/html")
            ) {
              return new Response("Not Found", {
                status: 404,
                statusText: "Not Found",
              });
            }
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        });
      }),
    );
  }
});
