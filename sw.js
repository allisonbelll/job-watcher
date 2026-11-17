/* Service worker: the app shell is cached on install; every request goes to
   the network first and falls back to the cache, so online visitors always
   get fresh data and offline visitors get the last data they loaded. */
const CACHE = "job-watcher-v1";
const SHELL = [
  "./", "index.html", "browse.html", "market.html",
  "assets/style.css", "assets/common.js", "assets/today.js", "assets/browse.js", "assets/market.js",
  "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png",
  "data/status.json", "data/history.csv",
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim()));
});

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const res = await fetch(req, { cache: "no-store" });
      if (res.ok) cache.put(req, res.clone());
      return res;
    } catch (err) {
      const hit = await cache.match(req, { ignoreSearch: true });
      if (hit) return hit;
      if (req.mode === "navigate") return (await cache.match("index.html")) || Response.error();
      return Response.error();
    }
  })());
});
