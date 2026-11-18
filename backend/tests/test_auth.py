from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Organization, User, UserRole

REGISTER_PAYLOAD = {
    "organization_name": "Тестовый парк",
    "name": "Админ Парка",
    "email": "admin@example.com",
    "password": "strong-password",
}


def register(client: TestClient, **overrides: str) -> dict:
    response = client.post("/api/v1/auth/register-org", json={**REGISTER_PAYLOAD, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def test_register_org_creates_admin_and_sets_cookie(
    client: TestClient, db_session: Session
) -> None:
    body = register(client)

    assert body["user"]["role"] == "admin"
    assert body["user"]["email"] == "admin@example.com"
    assert body["organization"]["name"] == "Тестовый парк"
    assert "password" not in str(body)

    stored = db_session.scalar(select(User))
    assert stored is not None
    assert stored.password_hash.startswith("$argon2")
    assert stored.role is UserRole.admin
    assert db_session.scalar(select(Organization)) is not None

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["id"] == body["user"]["id"]


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    register(client)

    response = client.post("/api/v1/auth/register-org", json=REGISTER_PAYLOAD)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_me_requires_cookie(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "unauthorized", "message": "Требуется вход в систему"}
    }


def test_login_logout_flow(client: TestClient) -> None:
    register(client)
    client.post("/api/v1/auth/logout")
    client.cookies.clear()

    assert client.get("/api/v1/auth/me").status_code == 401

    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "wrong-password"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "invalid_credentials"
    assert "access_token" not in client.cookies

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "ADMIN@example.com", "password": "strong-password"},
    )
    assert login.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_create_user_requires_admin(client: TestClient) -> None:
    register(client)

    created = client.post(
        "/api/v1/users",
        json={
            "name": "Менеджер",
            "email": "manager@example.com",
            "password": "manager-password",
            "role": "manager",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "manager"

    client.cookies.clear()
    client.post(
        "/api/v1/auth/login",
        json={"email": "manager@example.com", "password": "manager-password"},
    )

    forbidden = client.post(
        "/api/v1/users",
        json={
            "name": "Водитель",
            "email": "driver@example.com",
            "password": "driver-password",
            "role": "driver",
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "forbidden"


def test_create_user_rejects_duplicate_email(client: TestClient) -> None:
    register(client)

    response = client.post(
        "/api/v1/users",
        json={
            "name": "Второй админ",
            "email": "admin@example.com",
            "password": "another-password",
            "role": "manager",
        },
    )

    assert response.status_code == 409


def test_create_user_ignores_org_id_from_request_body(
    client: TestClient, db_session: Session
) -> None:
    register(client)
    other_org = Organization(name="Чужой парк")
    db_session.add(other_org)
    db_session.commit()

    response = client.post(
        "/api/v1/users",
        json={
            "name": "Водитель",
            "email": "driver@example.com",
            "password": "driver-password",
            "role": "driver",
            "org_id": str(other_org.id),
        },
    )

    assert response.status_code == 201, response.text
    created = db_session.scalar(select(User).where(User.email == "driver@example.com"))
    assert created is not None
    assert created.org_id != other_org.id
    assert created.org_id == db_session.scalar(select(User.org_id).where(User.role == "admin"))


def test_tampered_token_is_rejected(client: TestClient) -> None:
    client.cookies.set("access_token", "not-a-real-jwt")

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_short_password_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register-org", json={**REGISTER_PAYLOAD, "password": "short"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
