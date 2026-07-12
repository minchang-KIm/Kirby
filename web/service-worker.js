const CACHE = "windsprig-v1.0.0";
const CORE = Object.freeze([
  "/",
  "/manifest.webmanifest",
  "/favicon.png",
  "/social-card.png",
  "/build-info.json",
]);
const NETWORK_FIRST = new Set(["/build-info.json", "/service-worker.js"]);

function canCache(response) {
  return response.ok && response.type !== "opaque";
}

async function store(request, response) {
  if (!canCache(response)) return;
  const cache = await caches.open(CACHE);
  await cache.put(request, response.clone());
}

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => cache.addAll(CORE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(key => key !== CACHE).map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET" || request.headers.has("range")) return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Navigations and release identity revalidate; immutable runtime bytes are cache-first.
  const networkFirst = request.mode === "navigate" || NETWORK_FIRST.has(url.pathname);
  if (networkFirst) {
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        await store(request, response);
        return response;
      } catch {
        return (await caches.match(request)) || Response.error();
      }
    })());
    return;
  }

  event.respondWith((async () => {
    const hit = await caches.match(request);
    if (hit) return hit;
    const response = await fetch(request);
    await store(request, response);
    return response;
  })());
});
