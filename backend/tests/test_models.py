from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    ChatMessage,
    ChatRole,
    Damage,
    DamageSeverity,
    DamageSource,
    DamageType,
    Inspection,
    InspectionKind,
    InspectionStatus,
    LlmUsage,
    Organization,
    Photo,
    PhotoSide,
    Report,
    User,
    UserRole,
    Vehicle,
)


@dataclass
class Seed:
    org: Organization
    admin: User
    vehicle: Vehicle
    before: Inspection
    after: Inspection
    photo: Photo
    damage: Damage
    report: Report


def seed_inspection(db_session: Session) -> Seed:
    org = Organization(name="Тестовый парк")
    admin = User(
        organization=org,
        email="admin@example.com",
        password_hash="argon2-hash",
        name="Админ",
        role=UserRole.admin,
    )
    vehicle = Vehicle(organization=org, plate="A123BC", model="Kia Rio", year=2021)
    # UUID по умолчанию вычисляется на INSERT, поэтому фиксируем id до создания org_id-ссылок.
    db_session.add_all([org, admin, vehicle])
    db_session.flush()

    pair_id = uuid4()

    before = Inspection(
        org_id=org.id,
        vehicle=vehicle,
        driver=admin,
        kind=InspectionKind.before,
        pair_id=pair_id,
        status=InspectionStatus.done,
    )
    after = Inspection(
        org_id=org.id,
        vehicle=vehicle,
        driver=admin,
        kind=InspectionKind.after,
        pair_id=pair_id,
        status=InspectionStatus.processing,
    )
    photo = Photo(
        inspection=after,
        side=PhotoSide.front,
        storage_key="photos/2026/11/front.jpg",
        width=1920,
        height=1080,
        quality_score=0.92,
        quality_flags=["blurry"],
    )
    damage = Damage(
        org_id=org.id,
        inspection=after,
        photo=photo,
        type=DamageType.scratch,
        zone="front_left",
        severity=DamageSeverity.medium,
        confidence=0.81,
        polygon=[[0.12, 0.4], [0.18, 0.41], [0.17, 0.45]],
        source=DamageSource.cv,
        is_new=True,
    )
    report = Report(
        org_id=org.id,
        vehicle=vehicle,
        before_inspection=before,
        after_inspection=after,
        body={"summary": "Обнаружено новое повреждение"},
        text="Обнаружено повреждение на передней левой двери.",
        est_cost_min=Decimal("3000.00"),
        est_cost_max=Decimal("5000.00"),
    )
    chat = ChatMessage(org_id=org.id, user_id=admin.id, role=ChatRole.user, content="Что нового?")
    usage = LlmUsage(org_id=org.id, kind="report", input_tokens=120, output_tokens=80)

    db_session.add_all([org, admin, vehicle, before, after, photo, damage, report, chat, usage])
    db_session.commit()

    return Seed(
        org=org,
        admin=admin,
        vehicle=vehicle,
        before=before,
        after=after,
        photo=photo,
        damage=damage,
        report=report,
    )


def test_inspection_graph_roundtrip(db_session: Session) -> None:
    data = seed_inspection(db_session)

    loaded = db_session.get(Inspection, data.after.id)

    assert loaded is not None
    assert loaded.status is InspectionStatus.processing
    assert loaded.kind is InspectionKind.after
    assert loaded.pair_id == data.before.pair_id
    assert len(loaded.photos) == 1
    assert loaded.photos[0].quality_flags == ["blurry"]
    assert len(loaded.damages) == 1
    assert loaded.damages[0].polygon == [[0.12, 0.4], [0.18, 0.41], [0.17, 0.45]]
    assert loaded.damages[0].is_new is True
    assert db_session.scalar(select(Report).where(Report.after_inspection_id == loaded.id))
    assert db_session.scalar(select(ChatMessage))
    assert db_session.scalar(select(LlmUsage))


def test_enum_values_are_stored_in_lowercase(db_session: Session) -> None:
    seed_inspection(db_session)

    roles = db_session.scalars(select(User.role)).all()

    assert roles == [UserRole.admin]
    assert roles[0].value == "admin"


def test_vehicle_plate_is_unique_per_organization(db_session: Session) -> None:
    data = seed_inspection(db_session)

    other_org = Organization(name="Другой парк")
    db_session.add(other_org)
    db_session.flush()

    db_session.add(Vehicle(organization=other_org, plate="A123BC", model="Hyundai Solaris"))
    db_session.flush()  # тот же номер в другой организации — допустимо

    db_session.add(Vehicle(organization=data.org, plate="A123BC", model="Kia Rio"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_photo_side_is_unique_per_inspection(db_session: Session) -> None:
    data = seed_inspection(db_session)

    db_session.add(
        Photo(
            inspection=data.after,
            side=PhotoSide.front,
            storage_key="photos/2026/11/front-2.jpg",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_pair_has_one_inspection_per_kind(db_session: Session) -> None:
    data = seed_inspection(db_session)

    db_session.add(
        Inspection(
            org_id=data.before.org_id,
            vehicle_id=data.before.vehicle_id,
            driver_id=data.before.driver_id,
            kind=InspectionKind.before,
            pair_id=data.before.pair_id,
            status=InspectionStatus.draft,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_inspection_removes_photos_and_damages(db_session: Session) -> None:
    data = seed_inspection(db_session)
    extra = Inspection(
        org_id=data.org.id,
        vehicle=data.vehicle,
        driver=data.admin,
        kind=InspectionKind.after,
        status=InspectionStatus.draft,
    )
    extra_photo = Photo(inspection=extra, side=PhotoSide.back, storage_key="photos/back.jpg")
    extra_damage = Damage(
        org_id=data.org.id,
        inspection=extra,
        photo=extra_photo,
        type=DamageType.dent,
        confidence=0.6,
        polygon=[[0.1, 0.1], [0.2, 0.2], [0.15, 0.3]],
        source=DamageSource.cv,
    )
    db_session.add_all([extra, extra_photo, extra_damage])
    db_session.commit()

    db_session.delete(extra)
    db_session.commit()

    assert db_session.get(Photo, extra_photo.id) is None
    assert db_session.get(Damage, extra_damage.id) is None
