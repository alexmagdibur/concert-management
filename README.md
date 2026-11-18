# Concert CRM

Backend scaffold for one musical artist. Requirements: the NIRS PDF in the repository root, sections 1.6 and 1.10; development rules: AGENTS.md. The 12-table physical database model is implemented. See [database documentation](docs/database.md) for constraints, Docker setup and PostgreSQL tests.

## Запуск через Docker Compose

Требуется Docker Engine или Docker Desktop с Compose v2 и поддержкой Linux-контейнеров.
Если Docker Desktop установлен для текущего пользователя, а PowerShell не находит
`docker`, добавь его каталог в PATH текущего терминала.

```powershell
$env:Path = (Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin') + ';' + $env:Path
```

В корне проекта создай локальный `.env` из `.env.example`, если его ещё нет, и заполни
`POSTGRES_PASSWORD` собственным паролем. Для локального входа по HTTP используй
`APP_ENV=development` и `SESSION_COOKIE_SECURE=false`. Compose подключает backend к
PostgreSQL по внутреннему имени `postgres`. Переменная `DATABASE_URL` из локального
запуска применяется только вне Compose.

```powershell
docker compose up -d --build
docker compose ps --all
```

Интерфейс доступен на [127.0.0.1:8080](http://127.0.0.1:8080/).
Изменить порт можно через `FRONTEND_PORT`. Запросы по `/api/` проходят через Nginx во внутренний
FastAPI. Проверка всего пути до PostgreSQL доступна по
[`/api/ready`](http://127.0.0.1:8080/api/ready). Backend и PostgreSQL доступны внутри Docker-сетей.

Одноразовый сервис `migrate` ждёт готовности PostgreSQL, выполняет `alembic upgrade head` и
завершается с кодом 0. Backend стартует после успешной миграции. Если она завершилась с
ошибкой, проверь `docker compose logs migrate` перед повторным запуском.
Перед обновлением существующей установки сделай резервную копию БД, останови
`docker compose stop frontend backend`, затем снова выполни `docker compose up -d --build`.

На чистой БД создай первого администратора. Команда запрашивает пароль интерактивно.

```powershell
docker compose exec backend python -m app.bootstrap_admin --login crm_admin --full-name "Администратор CRM"
```

Войди под администратором, создай пользователя с ролью «Менеджер», затем войди под ним.
Для проверки сохранности создай площадку в справочнике, перезапусти сервисы и найди её снова
после того, как `docker compose ps` покажет состояние `healthy`.

```powershell
docker compose restart postgres backend frontend
docker compose ps
```

`docker compose stop` останавливает сервисы. `docker compose down` удаляет контейнеры и сети,
сохраняя именованный том `postgres_data`. Для возобновления работы выполни
`docker compose up -d` из того же каталога с тем же именем проекта. Если меняешь
`POSTGRES_PASSWORD` для уже созданного тома, сначала измени пароль роли в PostgreSQL:
переменная официального образа задаёт пароль при инициализации пустого тома.

Для production установи `APP_ENV=production` и `SESSION_COOKIE_SECURE=true`. Размести
HTTPS-прокси перед loopback-портом frontend и обслуживай интерфейс и `/api/` с одного
публичного HTTPS-адреса. Храни `.env` и TLS-ключи за пределами образов и Git.

## Run without Docker (PowerShell, repository root)

```powershell
py -3.14 -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
cd backend
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Configure APP_NAME and DATABASE_URL in the root .env. The example has no credentials; provide local PostgreSQL credentials privately. .env is ignored by Git.

GET http://127.0.0.1:8000/health returns HTTP 200 and `{"status":"ok"}`. This is an application liveness check, not a database readiness check. Swagger: http://127.0.0.1:8000/docs.

## Checks (from backend)

```powershell
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m alembic heads
```

## Database and layout

SQLAlchemy 2 uses PostgreSQL through psycopg. Provision PostgreSQL separately. get_session closes sessions; services will own transactions for related changes. No create_all is used. Alembic uses Base metadata. Apply the initial schema with `alembic upgrade head`. Future model changes require reviewed migrations.

Backend packages: core, models, schemas, repositories, services, routers. The React frontend uses the same API and PostgreSQL-backed sessions. See [frontend setup](frontend/README.md) for local startup, production build and browser verification.

## Test data

See [safe PostgreSQL seed](docs/seed.md) for the explicit CLI command, guards, dataset and tests. Seed never runs automatically.

## Catalog API

See [FR030 / UC03 REST API](docs/catalog-api.md) for routes, session access, validation and PostgreSQL tests.

## Concert API

See [FR040 / FR050 / UC04 concert API](docs/concert-api.md) for lifecycle, requests, search and PostgreSQL concurrency guarantees.

## Accounts and sessions

See [access API](docs/access-api.md) for initial administrator setup, cookies, CSRF and audit.
