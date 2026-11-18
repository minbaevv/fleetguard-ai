# FleetGuard AI — frontend

Next.js (App Router) + TypeScript + Tailwind CSS.

## Запуск

Нужен запущенный backend на `http://127.0.0.1:8000`.

```bash
npm install
cp .env.example .env    # при необходимости поправить BACKEND_URL
npm run dev
```

Откройте http://localhost:3000 — приложение перенаправит на `/login`.

`BACKEND_URL` используется в `next.config.ts` для rewrite `/api/*` → FastAPI. Браузер обращается
к тому же origin, поэтому httpOnly-cookie `access_token` работает без CORS.

## Проверки

```bash
npm run lint
npm run build
```

## Страницы

| Путь | Назначение |
|---|---|
| `/login` | вход по email и паролю |
| `/register` | регистрация организации и первого администратора |
| `/vehicles` | машины организации: список, поиск, добавление и удаление для admin/manager |

`/` перенаправляет на `/vehicles`; неавторизованный пользователь попадает на `/login`.
