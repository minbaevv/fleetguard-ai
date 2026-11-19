from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Damage,
    DamageSeverity,
    DamageSource,
    DamageType,
    Inspection,
    InspectionKind,
    InspectionStatus,
    Organization,
    Photo,
    PhotoSide,
    User,
    UserRole,
    Vehicle,
)
from app.main import app
from app.services.storage import get_storage

ADMIN = {
    "organization_name": "Парк А",
    "name": "Админ А",
    "email": "admin@a.example",
    "password": "admin-password",
}
ALL_SIDES = ["front", "back", "left", "right"]


class FakeStorage:
    def presigned_get_url(self, key: str, expires_in: int | None = None) -> str:
        return f"https://storage.test/{key}"


@pytest.fixture
def fake_storage(client: TestClient) -> Iterator[None]:
    app.dependency_overrides[get_storage] = lambda: FakeStorage()
    yield
    app.dependency_overrides.pop(get_storage, None)


def register(client: TestClient, payload: dict[str, str] | None = None) -> dict:
    response = client.post("/api/v1/auth/register-org", json=payload or ADMIN)
    assert response.status_code == 201, response.text
    return response.json()


def create_vehicle(client: TestClient, plate: str = "A123BC") -> dict:
    response = client.post(
        "/api/v1/vehicles", json={"plate": plate, "model": "Kia Rio", "year": 2021}
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_inspection(
    client: TestClient, vehicle_id: str, kind: str, pair_id: str | None = None
) -> dict:
    payload: dict[str, str] = {"vehicle_id": vehicle_id, "kind": kind}
    if pair_id is not None:
        payload["pair_id"] = pair_id
    response = client.post("/api/v1/inspections", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def add_photos(db_session: Session, inspection_id: str, sides: list[str] | None = None) -> None:
    for side in sides or ALL_SIDES:
        db_session.add(
            Photo(
                inspection_id=UUID(inspection_id),
                side=PhotoSide(side),
                storage_key=f"photos/{inspection_id}/{side}.jpg",
                width=1600,
                height=1200,
                quality_score=0.9,
                quality_flags=[],
            )
        )
    db_session.commit()


def finish(client: TestClient, inspection_id: str) -> None:
    response = client.post(f"/api/v1/inspections/{inspection_id}/finish")
    assert response.status_code == 202, response.text


def make_foreign_inspection(db_session: Session) -> Inspection:
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

    inspection = Inspection(
        org_id=org.id,
        vehicle_id=vehicle.id,
        driver_id=user.id,
        kind=InspectionKind.before,
        pair_id=uuid4(),
        status=InspectionStatus.processing,
        finished_at=datetime.now(UTC),
    )
    db_session.add(inspection)
    db_session.commit()
    return inspection


def test_create_before_starts_draft_with_required_sides(client: TestClient) -> None:
    register(client)
    vehicle = create_vehicle(client)

    body = create_inspection(client, vehicle["id"], "before")

    assert body["status"] == "draft"
    assert body["kind"] == "before"
    assert UUID(body["pair_id"])
    assert body["required_sides"] == ALL_SIDES


def test_create_after_requires_pair_id(client: TestClient) -> None:
    register(client)
    vehicle = create_vehicle(client)

    response = client.post(
        "/api/v1/inspections", json={"vehicle_id": vehicle["id"], "kind": "after"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "pair_id_required"


def test_before_rejects_client_pair_id(client: TestClient) -> None:
    register(client)
    vehicle = create_vehicle(client)

    response = client.post(
        "/api/v1/inspections",
        json={"vehicle_id": vehicle["id"], "kind": "before", "pair_id": str(uuid4())},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "pair_id_not_allowed"


def test_after_with_unknown_pair_returns_404(client: TestClient) -> None:
    register(client)
    vehicle = create_vehicle(client)

    response = client.post(
        "/api/v1/inspections",
        json={"vehicle_id": vehicle["id"], "kind": "after", "pair_id": str(uuid4())},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "inspection_pair_not_found"


def test_create_rejects_unknown_kind(client: TestClient) -> None:
    register(client)
    vehicle = create_vehicle(client)

    response = client.post(
        "/api/v1/inspections", json={"vehicle_id": vehicle["id"], "kind": "during"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_before_after_flow_links_pair(client: TestClient, db_session: Session) -> None:
    register(client)
    vehicle = create_vehicle(client)
    before = create_inspection(client, vehicle["id"], "before")
    add_photos(db_session, before["id"])
    finish(client, before["id"])

    after = create_inspection(client, vehicle["id"], "after", before["pair_id"])

    assert after["pair_id"] == before["pair_id"]
    assert after["kind"] == "after"
    assert after["status"] == "draft"

    add_photos(db_session, after["id"])
    finish(client, after["id"])

    detail = client.get(f"/api/v1/inspections/{after['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "processing"


def test_after_is_rejected_until_before_is_finished(client: TestClient) -> None:
    register(client)
    vehicle = create_vehicle(client)
    before = create_inspection(client, vehicle["id"], "before")

    response = client.post(
        "/api/v1/inspections",
        json={"vehicle_id": vehicle["id"], "kind": "after", "pair_id": before["pair_id"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "before_not_finished"


def test_second_after_for_pair_is_rejected(client: TestClient, db_session: Session) -> None:
    register(client)
    vehicle = create_vehicle(client)
    before = create_inspection(client, vehicle["id"], "before")
    add_photos(db_session, before["id"])
    finish(client, before["id"])
    create_inspection(client, vehicle["id"], "after", before["pair_id"])

    response = client.post(
        "/api/v1/inspections",
        json={"vehicle_id": vehicle["id"], "kind": "after", "pair_id": before["pair_id"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pair_complete"


def test_pair_must_belong_to_same_vehicle(client: TestClient, db_session: Session) -> None:
    register(client)
    first = create_vehicle(client, plate="A123BC")
    second = create_vehicle(client, plate="C456DE")
    before = create_inspection(client, first["id"], "before")
    add_photos(db_session, before["id"])
    finish(client, before["id"])

    response = client.post(
        "/api/v1/inspections",
        json={"vehicle_id": second["id"], "kind": "after", "pair_id": before["pair_id"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pair_vehicle_mismatch"


def test_finish_requires_all_four_sides(client: TestClient, db_session: Session) -> None:
    register(client)
    vehicle = create_vehicle(client)
    before = create_inspection(client, vehicle["id"], "before")
    add_photos(db_session, before["id"], ["front", "back"])

    response = client.post(f"/api/v1/inspections/{before['id']}/finish")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "inspection_incomplete"
    assert "left" in error["message"]
    assert "right" in error["message"]


def test_finish_twice_is_rejected(client: TestClient, db_session: Session) -> None:
    register(client)
    vehicle = create_vehicle(client)
    before = create_inspection(client, vehicle["id"], "before")
    add_photos(db_session, before["id"])
    finish(client, before["id"])

    response = client.post(f"/api/v1/inspections/{before['id']}/finish")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "inspection_not_draft"


def test_failed_inspection_cannot_be_finished(client: TestClient, db_session: Session) -> None:
    register(client)
    vehicle = create_vehicle(client)
    before = create_inspection(client, vehicle["id"], "before")
    add_photos(db_session, before["id"])
    inspection = db_session.get(Inspection, UUID(before["id"]))
    inspection.status = InspectionStatus.failed
    inspection.failure_reason = "detector crashed"
    db_session.commit()

    response = client.post(f"/api/v1/inspections/{before['id']}/finish")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "inspection_not_draft"


def test_get_unknown_inspection_returns_404(client: TestClient) -> None:
    register(client)

    response = client.get(f"/api/v1/inspections/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "inspection_not_found"


def test_get_inspection_returns_photos_and_damages(
    client: TestClient, db_session: Session, fake_storage: None
) -> None:
    register(client)
    vehicle = create_vehicle(client)
    before = create_inspection(client, vehicle["id"], "before")
    add_photos(db_session, before["id"], ["front"])
    inspection = db_session.get(Inspection, UUID(before["id"]))
    photo = db_session.scalar(select(Photo).where(Photo.inspection_id == inspection.id))
    db_session.add(
        Damage(
            org_id=inspection.org_id,
            inspection_id=inspection.id,
            photo_id=photo.id,
            type=DamageType.scratch,
            zone="door_left",
            severity=DamageSeverity.medium,
            confidence=0.81,
            polygon=[[0.12, 0.4], [0.18, 0.41], [0.17, 0.45]],
            source=DamageSource.cv,
            is_new=True,
        )
    )
    db_session.commit()

    response = client.get(f"/api/v1/inspections/{before['id']}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert len(body["photos"]) == 1
    photo_body = body["photos"][0]
    assert photo_body["side"] == "front"
    assert photo_body["url"] == f"https://storage.test/photos/{before['id']}/front.jpg"
    assert len(photo_body["damages"]) == 1
    damage = photo_body["damages"][0]
    assert damage["type"] == "scratch"
    assert damage["severity"] == "medium"
    assert damage["is_new"] is True
    assert damage["polygon"] == [[0.12, 0.4], [0.18, 0.41], [0.17, 0.45]]


def test_org_isolation_for_inspections(client: TestClient, db_session: Session) -> None:
    register(client)
    own_vehicle = create_vehicle(client)
    foreign = make_foreign_inspection(db_session)

    assert client.get(f"/api/v1/inspections/{foreign.id}").status_code == 404
    assert client.post(f"/api/v1/inspections/{foreign.id}/finish").status_code == 404
    response = client.post(
        "/api/v1/inspections",
        json={"vehicle_id": str(foreign.vehicle_id), "kind": "before"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "vehicle_not_found"

    # Чужой pair_id не находится даже для своей машины: фильтр по org_id обязателен.
    pair_response = client.post(
        "/api/v1/inspections",
        json={
            "vehicle_id": own_vehicle["id"],
            "kind": "after",
            "pair_id": str(foreign.pair_id),
        },
    )
    assert pair_response.status_code == 404
    assert pair_response.json()["error"]["code"] == "inspection_pair_not_found"


def test_driver_can_start_inspection(client: TestClient) -> None:
    register(client)
    vehicle = create_vehicle(client)
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
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "driver@a.example", "password": "driver-password"},
        ).status_code
        == 200
    )

    body = create_inspection(client, vehicle["id"], "before")
    assert body["status"] == "draft"


def test_requires_authentication(client: TestClient) -> None:
    assert (
        client.post(
            "/api/v1/inspections", json={"vehicle_id": str(uuid4()), "kind": "before"}
        ).status_code
        == 401
    )
    assert client.get(f"/api/v1/inspections/{uuid4()}").status_code == 401
    assert client.post(f"/api/v1/inspections/{uuid4()}/finish").status_code == 401
