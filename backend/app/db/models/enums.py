from enum import StrEnum


class UserRole(StrEnum):
    admin = "admin"
    manager = "manager"
    driver = "driver"


class InspectionKind(StrEnum):
    before = "before"
    after = "after"


class InspectionStatus(StrEnum):
    draft = "draft"
    uploading = "uploading"
    processing = "processing"
    done = "done"
    failed = "failed"


class PhotoSide(StrEnum):
    front = "front"
    back = "back"
    left = "left"
    right = "right"


class DamageType(StrEnum):
    dent = "dent"
    scratch = "scratch"
    crack = "crack"
    glass_shatter = "glass_shatter"
    lamp_broken = "lamp_broken"
    tire_flat = "tire_flat"


class DamageSeverity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class DamageSource(StrEnum):
    cv = "cv"
    llm = "llm"


class ChatRole(StrEnum):
    user = "user"
    assistant = "assistant"
