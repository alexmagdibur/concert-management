"""Run the browser scenario with live FastAPI and disposable PostgreSQL data."""

import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

from sqlalchemy import create_engine, make_url, text


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for_api(process: subprocess.Popen, api: str) -> None:
    deadline = monotonic() + 30
    while monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Backend exited before becoming ready")
        try:
            with urlopen(api + "/ready", timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            sleep(0.2)
    raise RuntimeError("Backend startup timed out")


def main() -> int:
    test_dsn = os.environ.get("TEST_DATABASE_URL")
    if not test_dsn:
        raise SystemExit(
            "Set TEST_DATABASE_URL to a disposable PostgreSQL test database."
        )
    frontend = Path(__file__).resolve().parents[1]
    backend = frontend.parent / "backend"
    sys.path.insert(0, str(backend))
    schema = "frontend_e2e_" + uuid4().hex
    db_url = make_url(test_dsn)
    if db_url.get_backend_name() != "postgresql":
        raise SystemExit("TEST_DATABASE_URL must point to PostgreSQL.")
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        options = db_url.query.get("options", "")
        test_url = db_url.update_query_dict(
            {"options": f"{options} -csearch_path={schema}".strip()}
        )
        os.environ.update(
            DATABASE_URL=test_url.render_as_string(hide_password=False),
            APP_ENV="test",
            SESSION_COOKIE_SECURE="false",
            E2E_ADMIN_LOGIN="frontend_e2e_admin",
            E2E_ADMIN_PASSWORD=secrets.token_urlsafe(24),
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend,
            check=True,
        )
        from app.core.database import SessionLocal
        from app.schemas.access import AccountCreate
        from app.services.users import UserService

        with SessionLocal() as session:
            UserService(session).create(
                AccountCreate(
                    full_name="E2E Administrator",
                    position="Administrator",
                    login=os.environ["E2E_ADMIN_LOGIN"],
                    password=os.environ["E2E_ADMIN_PASSWORD"],
                    roles=["ADMIN"],
                ),
                actor=None,
            )
        backend_port = free_port()
        frontend_port = free_port()
        while frontend_port == backend_port:
            frontend_port = free_port()
        api = f"http://127.0.0.1:{backend_port}"
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(backend_port),
                "--no-access-log",
            ],
            cwd=backend,
        )
        try:
            wait_for_api(process, api)
            env = os.environ | {
                "API_TARGET": api,
                "E2E_BASE_URL": f"http://127.0.0.1:{frontend_port}",
            }
            # Do not pass PostgreSQL DSNs to the frontend or to browser tooling.
            for key in ("DATABASE_URL", "TEST_DATABASE_URL", "SEED_DATABASE_URL"):
                env.pop(key, None)
            return subprocess.run(
                [
                    "node",
                    str(frontend / "node_modules/@playwright/test/cli.js"),
                    "test",
                ],
                cwd=frontend,
                env=env,
                check=False,
            ).returncode
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            SessionLocal.kw["bind"].dispose()
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
