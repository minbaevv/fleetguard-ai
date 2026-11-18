from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Inspection,
    InspectionKind,
    InspectionStatus,
    Organization,
    User,
    UserRole,
    Vehicle,
)

ADMIN = {
    "organization_name": "Парк А",
    "name": "Админ А",
    "email": "admin@a.example",
    "password": "admin-password",
}


def register(client: TestClient, payload: dict[str, str] | None = None) -> dict:
    response = client.post("/api/v1/auth/register-org", json=payload or ADMIN)
    assert response.status_code == 201, response.text
    return response.json()


def create_vehicle(
    client: TestClient, plate: str = "A123BC", model: str = "Kia Rio", year: int = 2021
) -> dict:
    response = client.post("/api/v1/vehicles", json={"plate": plate, "model": model, "year": year})
    assert response.status_code == 201, response.text
    return response.json()


def make_foreign_org(db_session: Session) -> tuple[Organization, Vehicle]:
    org = Organization(name="Парк Б")
    user = User(
        organization=org,
        email="admin@b.example",
        password_hash="not-a-real-hash",
        name="Админ Б",
        role=UserRole.admin,
    )
    vehicle = Vehicle(organization=org, plate="B999BB", model="Hyundai Solaris", year=2019)
    db_session.add_all([org, user, vehicle])
    db_session.commit()
    return org, vehicle


def test_create_list_and_search_vehicles(client: TestClient) -> None:
    register(client)

    created = create_vehicle(client, plate=" a123bc ", model="Kia Rio")

    assert created["plate"] == "A123BC"
    assert created["model"] == "Kia Rio"

    create_vehicle(client, plate="C456DE", model="Skoda Octavia")

    listed = client.get("/api/v1/vehicles")
    assert listed.status_code == 200
    assert [vehicle["plate"] for vehicle in listed.json()] == ["A123BC", "C456DE"]

    searched = client.get("/api/v1/vehicles", params={"search": "rio"})
    assert [vehicle["plate"] for vehicle in searched.json()] == ["A123BC"]

    single = client.get(f"/api/v1/vehicles/{created['id']}")
    assert single.status_code == 200
    assert single.json()["id"] == created["id"]


def test_duplicate_plate_in_same_org_is_rejected(client: TestClient) -> None:
    register(client)
    create_vehicle(client)

    response = client.post(
        "/api/v1/vehicles", json={"plate": "a123bc", "model": "Другая", "year": None}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "plate_taken"


def test_same_plate_is_allowed_in_another_org(client: TestClient, db_session: Session) -> None:
    register(client)
    make_foreign_org(db_session)

    response = client.post(
        "/api/v1/vehicles", json={"plate": "B999BB", "model": "Kia Rio", "year": 2021}
    )

    assert response.status_code == 201, response.text


def test_org_isolation_hides_foreign_vehicles(client: TestClient, db_session: Session) -> None:
    register(client)
    create_vehicle(client)
    _, foreign_vehicle = make_foreign_org(db_session)

    listed = client.get("/api/v1/vehicles")
    assert [vehicle["plate"] for vehicle in listed.json()] == ["A123BC"]

    vehicle_id = str(foreign_vehicle.id)
    assert client.get(f"/api/v1/vehicles/{vehicle_id}").status_code == 404
    assert (
        client.patch(f"/api/v1/vehicles/{vehicle_id}", json={"model": "Взлом"}).status_code == 404
    )
    assert client.delete(f"/api/v1/vehicles/{vehicle_id}").status_code == 404

    still_there = db_session.get(Vehicle, foreign_vehicle.id)
    assert still_there is not None
    assert still_there.model == "Hyundai Solaris"


def test_update_vehicle(client: TestClient) -> None:
    register(client)
    vehicle = create_vehicle(client)
    create_vehicle(client, plate="C456DE", model="Skoda Octavia")

    updated = client.patch(
        f"/api/v1/vehicles/{vehicle['id']}", json={"model": "Kia Rio X", "year": 2022}
    )
    assert updated.status_code == 200
    assert updated.json()["model"] == "Kia Rio X"
    assert updated.json()["year"] == 2022

    conflict = client.patch(f"/api/v1/vehicles/{vehicle['id']}", json={"plate": "c456de"})
    assert conflict.status_code == 409

    null_plate = client.patch(f"/api/v1/vehicles/{vehicle['id']}", json={"plate": None})
    assert null_plate.status_code == 422


def test_delete_vehicle(client: TestClient) -> None:
    register(client)
    vehicle = create_vehicle(client)

    response = client.delete(f"/api/v1/vehicles/{vehicle['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/vehicles/{vehicle['id']}").status_code == 404


def test_delete_vehicle_with_history_is_forbidden(client: TestClient, db_session: Session) -> None:
    register(client)
    vehicle = create_vehicle(client)
    admin = db_session.scalar(select(User).where(User.email == "admin@a.example"))
    assert admin is not None

    db_session.add(
        Inspection(
            org_id=admin.org_id,
            vehicle_id=UUID(vehicle["id"]),
            driver_id=admin.id,
            kind=InspectionKind.before,
            status=InspectionStatus.draft,
        )
    )
    db_session.commit()

    response = client.delete(f"/api/v1/vehicles/{vehicle['id']}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "vehicle_has_history"


def test_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/vehicles")

    assert response.status_code == 401


def test_driver_can_view_but_not_create(client: TestClient) -> None:
    register(client)
    created = client.post(
        "/api/v1/users",
        json={
            "name": "Водитель",
            "email": "driver@a.example",
            "password": "driver-password",
            "role": "driver",
        },
    )
    assert created.status_code == 201, created.text

    client.cookies.clear()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "driver@a.example", "password": "driver-password"},
    )
    assert login.status_code == 200

    assert client.get("/api/v1/vehicles").status_code == 200
    forbidden = client.post(
        "/api/v1/vehicles", json={"plate": "X000XX", "model": "Kia Rio", "year": 2020}
    )
    assert forbidden.status_code == 403


def test_validation_errors(client: TestClient) -> None:
    register(client)

    assert client.post("/api/v1/vehicles", json={"plate": " ", "model": "Kia"}).status_code == 422
    assert (
        client.post(
            "/api/v1/vehicles", json={"plate": "A123BC", "model": "Kia", "year": 1800}
        ).status_code
        == 422
    )
