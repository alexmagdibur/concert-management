from fastapi.testclient import TestClient

from app.core.security import COOKIE_NAME
from app.main import app

LOGIN_HEADER = {"X-Requested-With": "ConcertCRM"}
NO_SESSION = {"Cookie": ""}


def login(client, login_name, password):
    return client.post(
        "/auth/login", json={"login": login_name, "password": password}, headers=LOGIN_HEADER
    )


def sign_in(client, login_name, password):
    result = login(client, login_name, password)
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    return result


def session_headers(login_name, password):
    with TestClient(app, base_url="https://testserver") as client:
        result = sign_in(client, login_name, password)
        return {
            "Cookie": f"{COOKIE_NAME}={client.cookies[COOKIE_NAME]}",
            "X-CSRF-Token": result.json()["csrf_token"],
        }
