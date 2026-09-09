// sw.js — Service Worker для PWA

const CACHE_NAME = 'quantum-bet-tracker-v15';
const STATIC_CACHE_NAME = 'quantum-bet-tracker-static-v15';

// Файлы для кеширования
const STATIC_ASSETS = [
  '/',
  '/static/IMG_2820.jpeg',
  '/static/manifest.json'
];

// Динамические ресурсы, которые кешируются при первом запросе
const DYNAMIC_ASSETS = [
  'https://cdn.jsdelivr.net/npm/chart.js',
  'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js'
];

// Устанавливаем service worker
self.addEventListener('install', (event) => {
  console.log('[SW] Установка...');
  event.waitUntil(
    caches.open(STATIC_CACHE_NAME)
      .then((cache) => {
        console.log('[SW] Кеширование статики');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        // Кешируем динамические ресурсы (CDN)
        return caches.open(CACHE_NAME);
      })
      .then((cache) => {
        return cache.addAll(DYNAMIC_ASSETS).catch(() => {
          console.log('[SW] Некоторые CDN ресурсы недоступны');
        });
      })
      .then(() => {
        console.log('[SW] Установка завершена');
        return self.skipWaiting();
      })
  );
});

// Активируем service worker
self.addEventListener('activate', (event) => {
  console.log('[SW] Активация...');
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => {
              return name !== CACHE_NAME && name !== STATIC_CACHE_NAME;
            })
            .map((name) => {
              console.log('[SW] Удаление старого кеша:', name);
              return caches.delete(name);
            })
        );
      })
      .then(() => {
        console.log('[SW] Активация завершена');
        return self.clients.claim();
      })
  );
});

// Обрабатываем запросы
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  
  // Пропускаем API запросы (они должны всегда идти на сервер)
  if (url.pathname.startsWith('/api/') || url.pathname.includes('/api/')) {
    // Для API используем стратегию "сначала сеть"
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // Кешируем успешные ответы API для офлайн-режима
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, clone);
            });
          }
          return response;
        })
        .catch(() => {
          // Если сеть недоступна, пытаемся взять из кеша
          return caches.match(event.request);
        })
    );
    return;
  }

  // Для статических ресурсов используем "сначала кеш, потом сеть"
  event.respondWith(
    caches.match(event.request)
      .then((cachedResponse) => {
        if (cachedResponse) {
          // Обновляем кеш в фоне
          fetch(event.request)
            .then((response) => {
              if (response && response.status === 200) {
                caches.open(STATIC_CACHE_NAME).then((cache) => {
                  cache.put(event.request, response);
                });
              }
            })
            .catch(() => {});
          return cachedResponse;
        }
        
        return fetch(event.request)
          .then((response) => {
            // Если ресурс статический, кешируем его
            if (response && response.status === 200) {
              const clone = response.clone();
              caches.open(STATIC_CACHE_NAME).then((cache) => {
                cache.put(event.request, clone);
              });
            }
            return response;
          })
          .catch(() => {
            // Если ресурс не найден в кеше и сеть недоступна
            if (event.request.mode === 'navigate') {
              return caches.match('/index.html') || caches.match('/');
            }
            return new Response('Сеть недоступна', {
              status: 503,
              statusText: 'Service Unavailable'
            });
          });
      })
  );
});

// Обработка push-уведомлений (опционально)
self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || 'Quantum Bet Tracker';
  const options = {
    body: data.body || 'Новое обновление!',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/icon-72x72.png',
    vibrate: [200, 100, 200],
    data: {
      url: data.url || '/'
    },
    actions: [
      {
        action: 'open',
        title: 'Открыть'
      }
    ]
  };
  
  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// Обработка клика по уведомлению
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  const url = event.notification.data?.url || '/';
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          if (client.url === url && 'focus' in client) {
            return client.focus();
          }
        }
        if (clients.openWindow) {
          return clients.openWindow(url);
        }
      })
  );
});
