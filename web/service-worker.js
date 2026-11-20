/* Service worker d'Aya.
   Stratégie : le réseau d'abord pour la page et les scripts (on a toujours la
   dernière version quand on est en ligne), le cache seulement en secours hors
   ligne. Le nom du cache change à chaque version pour purger l'ancien. */
const VERSION = "2026-11-20-1";
const CACHE = "aya-shell-" + VERSION;
const SHELL = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/manifest.webmanifest",
  "/static/icons/icon-192-v3.png",
  "/static/icons/icon-512-v3.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  // Réseau d'abord : jamais de vieille version servie quand on est connecté.
  event.respondWith(
    fetch(request, { cache: "no-store" })
      .then((response) => {
        if (response.ok && response.type === "basic") {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match("/")))
  );
});
