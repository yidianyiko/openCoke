from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa

from coke import schema
from coke.domains.identity_access.passwords import PasswordHasher
from scripts.ops.migrate_coke_clean_credentials import (
    TARGET_CREDENTIALS,
    _stable_user_profile_id,
    migrate_credentials,
)


def _setup_db():
    engine = sa.create_engine("sqlite:///:memory:")
    schema.account.create(engine)
    schema.user_profile.create(engine)
    schema.credential.create(engine)
    return engine


def _insert_account_and_credential(
    conn,
    *,
    account_id: str,
    email: str,
    password_hash: str,
    display_name: str | None = None,
) -> None:
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
    if display_name is not None:
        conn.execute(
            schema.user_profile.insert().values(
                id=_stable_user_profile_id(account_id),
                account_id=account_id,
                real_name=None,
                nickname=display_name,
                description=None,
                relationship_description=None,
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
        assert result.profiles_created == 2
        assert result.profiles_skipped == 0
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
        profiles = conn.execute(
            sa.select(
                schema.user_profile.c.account_id,
                schema.user_profile.c.nickname,
            ).order_by(schema.user_profile.c.account_id)
        ).mappings().all()
        assert {row["nickname"] for row in profiles} == {
            target.display_name for target in TARGET_CREDENTIALS
        }
        assert conn.execute(sa.select(sa.func.count()).select_from(schema.account)).scalar_one() == 2


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
            display_name=target.display_name,
        )

        result = migrate_credentials(conn, targets=[target], hasher=hasher)

        assert result.updated == 0
        assert result.skipped == 1
        assert result.profiles_created == 0
        assert result.profiles_skipped == 1
        row = conn.execute(sa.select(schema.credential.c.password_hash)).mappings().one()
        assert row["password_hash"] == existing_hash
        profile_count = conn.execute(
            sa.select(sa.func.count()).select_from(schema.user_profile)
        ).scalar_one()
        assert profile_count == 1


def test_migrate_credentials_reports_missing_target_without_creating_rows():
    engine = _setup_db()

    with engine.begin() as conn:
        result = migrate_credentials(conn)

        assert result.updated == 0
        assert result.skipped == 0
        assert result.profiles_created == 0
        assert result.profiles_skipped == 0
        assert result.missing == [target.account_id for target in TARGET_CREDENTIALS]
        assert conn.execute(sa.select(sa.func.count()).select_from(schema.credential)).scalar_one() == 0
        assert conn.execute(sa.select(sa.func.count()).select_from(schema.user_profile)).scalar_one() == 0
