from __future__ import annotations

from pathlib import Path
from typing import Dict

from .auth_service import AuthError, AuthService


SEED_USERS = [
    {"username": "super_admin1", "role": "super_admin"},
    {"username": "admin1", "role": "admin"},
    {"username": "operator1", "role": "operator"},
    {"username": "user1", "role": "user"},
]

RAW_USER_FIELDS = [
    "id",
    "username",
    "password_salt",
    "password_hash",
    "created_at",
    "status",
    "role",
    "last_login_at",
    "password_updated_at",
    "updated_at",
]


def _sqlite_url(path: str) -> str:
    return f"sqlite:///{Path(path).resolve().as_posix()}"


def _signature(record: Dict[str, object]) -> Dict[str, object]:
    return {field: record.get(field) for field in RAW_USER_FIELDS}


def migrate_sqlite_users(source_sqlite_path: str, target_database_url: str) -> Dict[str, int]:
    source_service = AuthService(database_url=_sqlite_url(source_sqlite_path))
    target_service = AuthService(database_url=target_database_url)

    source_records = source_service.list_user_records()
    existing_records = target_service.list_user_records()
    by_id = {record["id"]: record for record in existing_records}
    by_username = {record["username"]: record for record in existing_records}

    migrated = 0
    skipped = 0
    for record in source_records:
        matched = by_id.get(record["id"]) or by_username.get(record["username"])
        if matched:
            if _signature(matched) != _signature(record):
                raise AuthError(f"user {record['username']} conflicts with existing target user")
            skipped += 1
            continue

        target_service.create_user_record(record)
        migrated += 1

    return {
        "scanned": len(source_records),
        "migrated": migrated,
        "skipped": skipped,
    }


def ensure_seed_users(target_database_url: str, seed_password: str = "ChangeMe123!") -> Dict[str, int]:
    service = AuthService(database_url=target_database_url)
    created = 0
    updated = 0

    for seed in SEED_USERS:
        existing = service.get_user_by_username(seed["username"])
        if not existing:
            created_user = service.register(seed["username"], seed_password)
            if seed["role"] != "user":
                service.update_user_role(created_user["id"], seed["role"])
            created += 1
            continue

        changed = False
        if existing["role"] != seed["role"]:
            service.update_user_role(existing["id"], seed["role"])
            changed = True

        refreshed = service.get_user_by_id(existing["id"])
        if refreshed and refreshed["status"] != "active":
            service.update_user_status(existing["id"], "active")
            changed = True

        if changed:
            updated += 1

    return {
        "created": created,
        "updated": updated,
        "total_seed_users": len(SEED_USERS),
    }
