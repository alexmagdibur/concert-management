# Frontend Concert CRM

React, TypeScript, Vite, React Router и TanStack Query. Все страницы используют FastAPI через префикс `/api`. Авторизация опирается на HttpOnly cookie, CSRF-токен хранится в памяти приложения и восстанавливается через `/auth/me`.

## Локальный запуск

Подготовьте PostgreSQL, примените миграции и создайте первого администратора по инструкции доступа. Для разработки на HTTP укажите в локальном корневом `.env` значения `APP_ENV=development` и `SESSION_COOKIE_SECURE=false`. Запустите backend на loopback. [Настройка доступа](../docs/access-api.md)

В отдельном терминале из каталога frontend с Node.js 24:

```powershell
npm.cmd ci
$env:API_TARGET = 'http://127.0.0.1:8000'
npm.cmd run dev
```

Откройте [http://127.0.0.1:5173](http://127.0.0.1:5173). Если backend запущен на другом порту, укажите его в `API_TARGET`. Войдите как администратор, создайте менеджера и войдите с его учётной записью для работы с концертами.

`npm.cmd run build` собирает приложение в `dist`. При размещении раздавайте этот каталог по HTTPS, направляйте `/api/*` в FastAPI без префикса `/api`, а маршруты приложения возвращайте в `index.html`. Для production используйте Secure cookie.

## Браузерная проверка

Укажите `TEST_DATABASE_URL` для отдельной PostgreSQL-базы с правом создания схем. Установите Chromium через `npx.cmd playwright install chromium` или задайте `E2E_BROWSER=msedge` для установленного Edge. Из каталога frontend выполните:

```powershell
..\backend\.venv\Scripts\python.exe e2e/run.py
```

Сценарий запускает временные FastAPI и Vite, выполняет операции через браузер и удаляет свою тестовую схему PostgreSQL. Для тестовых учётных записей генерируются временные пароли.
