// sw.js — Service Worker для PWA
// Quantum Bet Tracker v16

const CACHE_VERSION = 'v16';
const CACHE_NAME = `quantum-bet-tracker-${CACHE_VERSION}`;
const STATIC_CACHE_NAME = `quantum-bet-tracker-static-${CACHE_VERSION}`;

// ============================================================
// СТАТИЧЕСКИЕ РЕСУРСЫ (кэшируются при установке)
// ============================================================
const STATIC_ASSETS = [
  '/',
  '/static/IMG_2820.jpeg',
  '/static/manifest.json'
];

// CDN ресурсы
const DYNAMIC_ASSETS = [
  'https://cdn.jsdelivr.net/npm/chart.js',
  'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js'
];

// ============================================================
// УСТАНОВКА
// ============================================================
self.addEventListener('install', (event) => {
  console.log(`[SW ${CACHE_VERSION}] Установка...`);
  event.waitUntil(
    caches.open(STATIC_CACHE_NAME)
      .then((cache) => {
        console.log(`[SW ${CACHE_VERSION}] Кэширование статики`);
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => caches.open(CACHE_NAME))
      .then((cache) => {
        console.log(`[SW ${CACHE_VERSION}] Кэширование CDN`);
        return cache.addAll(DYNAMIC_ASSETS).catch(() => {
          console.log(`[SW ${CACHE_VERSION}] Некоторые CDN ресурсы недоступны`);
        });
      })
      .then(() => {
        console.log(`[SW ${CACHE_VERSION}] Установка завершена`);
        return self.skipWaiting();
      })
      .catch((err) => {
        console.error(`[SW ${CACHE_VERSION}] Ошибка установки:`, err);
      })
  );
});

// ============================================================
// АКТИВАЦИЯ — удаляем ВСЕ старые кэши
// ============================================================
self.addEventListener('activate', (event) => {
  console.log(`[SW ${CACHE_VERSION}] Активация...`);
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => {
              // Удаляем все кэши, кроме текущей версии
              return name !== CACHE_NAME && name !== STATIC_CACHE_NAME;
            })
            .map((name) => {
              console.log(`[SW ${CACHE_VERSION}] Удаление старого кэша:`, name);
              return caches.delete(name);
            })
        );
      })
      .then(() => {
        console.log(`[SW ${CACHE_VERSION}] Активация завершена`);
        return self.clients.claim();
      })
  );
});

// ============================================================
// FETCH — обработка запросов
// ============================================================
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // ─── 1. Игнорируем не-GET запросы ───
  // POST/PUT/DELETE никогда не кэшируем
  if (request.method !== 'GET') {
    return;  // пусть идёт напрямую
  }

  // ─── 2. API-запросы — СЕТЬ ПЕРВАЯ, КЭШ ТОЛЬКО ПРИ ОФЛАЙНЕ ───
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // ⚠️ ВАЖНО: кэшируем ТОЛЬКО успешные ответы (200 OK)
          // НЕ кэшируем 404, 500 и т.д.
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME)
              .then((cache) => cache.put(request, clone))
              .catch(() => {});
          }
          return response;
        })
        .catch(() => {
          // Сеть недоступна — пробуем кэш
          return caches.match(request).then((cached) => {
            if (cached) {
              console.log(`[SW ${CACHE_VERSION}] API из кэша (офлайн):`, url.pathname);
              return cached;
            }
            // В кэше нет — возвращаем JSON-ошибку
            return new Response(JSON.stringify({
              status: 'offline',
              error: 'Нет сети и данных в кэше'
            }), {
              status: 503,
              statusText: 'Service Unavailable',
              headers: { 'Content-Type': 'application/json; charset=utf-8' }
            });
          });
        })
    );
    return;
  }

  // ─── 3. Навигация (HTML-страницы) — СЕТЬ ПЕРВАЯ ───
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Всегда свежая версия HTML
          const clone = response.clone();
          caches.open(STATIC_CACHE_NAME)
            .then((cache) => cache.put(request, clone))
            .catch(() => {});
          return response;
        })
        .catch(() => {
          // Офлайн — отдаём закэшированный '/'
          return caches.match('/') || caches.match('/index.html');
        })
    );
    return;
  }

  // ─── 4. Всё остальное (статика) — КЭШ ПЕРВЫЙ, СЕТЬ В ФОНЕ ───
  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      // Запускаем фоновое обновление даже если есть кэш
      const fetchPromise = fetch(request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(STATIC_CACHE_NAME)
              .then((cache) => cache.put(request, clone))
              .catch(() => {});
          }
          return networkResponse;
        })
        .catch(() => null);

      // Если есть кэш — отдаём сразу, обновляем в фоне
      if (cachedResponse) {
        return cachedResponse;
      }

      // Нет кэша — ждём сеть
      return fetchPromise.then((response) => {
        if (response) return response;

        // Ни кэша, ни сети — отдаём заглушку
        return new Response('Сеть недоступна', {
          status: 503,
          statusText: 'Service Unavailable',
          headers: { 'Content-Type': 'text/plain; charset=utf-8' }
        });
      });
    })
  );
});

// ============================================================
// PUSH-УВЕДОМЛЕНИЯ
// ============================================================
self.addEventListener('push', (event) => {
  console.log(`[SW ${CACHE_VERSION}] Push получен`);
  const data = event.data ? event.data.json() : {};
  const title = data.title || 'Quantum Bet Tracker';
  const options = {
    body: data.body || 'Новое обновление!',
    icon: '/static/IMG_2820.jpeg',
    badge: '/static/IMG_2820.jpeg',
    vibrate: [200, 100, 200],
    data: {
      url: data.url || '/'
    },
    actions: [
      { action: 'open', title: 'Открыть' }
    ]
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// ============================================================
// КЛИК ПО УВЕДОМЛЕНИЮ
// ============================================================
self.addEventListener('notificationclick', (event) => {
  console.log(`[SW ${CACHE_VERSION}] Клик по уведомлению`);
  event.notification.close();

  const targetUrl = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Если уже открыто окно — фокусируемся
        for (const client of clientList) {
          if (client.url === targetUrl && 'focus' in client) {
            return client.focus();
          }
        }
        // Иначе открываем новое
        if (clients.openWindow) {
          return clients.openWindow(targetUrl);
        }
      })
  );
});

// ============================================================
// СООБЩЕНИЯ ОТ ГЛАВНОГО ПОТОКА (SKIP_WAITING)
// ============================================================
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    console.log(`[SW ${CACHE_VERSION}] SKIP_WAITING`);
    self.skipWaiting();
  }
});
