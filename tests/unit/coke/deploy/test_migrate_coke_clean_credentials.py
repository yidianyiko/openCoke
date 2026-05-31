from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa

from coke import schema
from coke.domains.identity_access.passwords import PasswordHasher
from scripts.ops.migrate_coke_clean_credentials import (
    TARGET_CREDENTIALS,
    migrate_credentials,
)


def _setup_db():
    engine = sa.create_engine("sqlite:///:memory:")
    schema.account.create(engine)
    schema.credential.create(engine)
    return engine


def _insert_account_and_credential(conn, *, account_id: str, email: str, password_hash: str) -> None:
    now = datetime(2026, 5, 31, tzinfo=timezone.utc)
    credential_id = f"0000000000000000000000000000000{account_id[-1]}"
    conn.execute(
        schema.account.insert().values(
            id=account_id,
            origin="web_first",
            default_timezone="Asia/Tokyo",
            lifecycle="active",
            created_at=now,
            updated_at=now,
        )
    )
    conn.execute(
        schema.credential.insert().values(
            id=credential_id,
            account_id=account_id,
            email=email,
            password_hash=password_hash,
            email_verified_at=now,
            reset_required=False,
            created_at=now,
            updated_at=now,
        )
    )


def test_migrate_credentials_updates_existing_rows_in_place_and_preserves_accounts():
    engine = _setup_db()
    hasher = PasswordHasher()

    with engine.begin() as conn:
        for target in TARGET_CREDENTIALS:
            _insert_account_and_credential(
                conn,
                account_id=target.account_id,
                email=target.email,
                password_hash=target.password,
            )

        result = migrate_credentials(conn, hasher=hasher)

        assert result.updated == 2
        assert result.skipped == 0
        assert result.missing == []

        rows = conn.execute(
            sa.select(
                schema.credential.c.email,
                schema.credential.c.password_hash,
            ).order_by(schema.credential.c.email)
        ).mappings().all()
        assert {row["email"] for row in rows} == {target.email for target in TARGET_CREDENTIALS}
        for row in rows:
            target = next(item for item in TARGET_CREDENTIALS if item.email == row["email"])
            assert row["email"] == target.email
            assert row["password_hash"] != target.password
            assert hasher.verify(row["password_hash"], target.password)


def test_migrate_credentials_is_idempotent_for_existing_argon2_hashes():
    engine = _setup_db()
    hasher = PasswordHasher()

    with engine.begin() as conn:
        target = TARGET_CREDENTIALS[0]
        existing_hash = hasher.hash(target.password)
        _insert_account_and_credential(
            conn,
            account_id=target.account_id,
            email=target.email,
            password_hash=existing_hash,
        )

        result = migrate_credentials(conn, targets=[target], hasher=hasher)

        assert result.updated == 0
        assert result.skipped == 1
        row = conn.execute(sa.select(schema.credential.c.password_hash)).mappings().one()
        assert row["password_hash"] == existing_hash


def test_migrate_credentials_reports_missing_target_without_creating_rows():
    engine = _setup_db()

    with engine.begin() as conn:
        result = migrate_credentials(conn)

        assert result.updated == 0
        assert result.skipped == 0
        assert result.missing == [target.account_id for target in TARGET_CREDENTIALS]
        assert conn.execute(sa.select(sa.func.count()).select_from(schema.credential)).scalar_one() == 0
