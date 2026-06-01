from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

T = TypeVar("T")


def json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [json_value(item) for item in value]
    if isinstance(value, list):
        return [json_value(item) for item in value]
    return value


def one_or_none(
    session: Session, table: sa.Table, *where: Any
) -> Mapping[str, Any] | None:
    statement = sa.select(table).where(*where)
    row = session.execute(statement).mappings().one_or_none()
    return _normalize_row(row) if row is not None else None


def many(
    session: Session, table: sa.Table, *where: Any, order_by: tuple[Any, ...] = ()
) -> list[Mapping[str, Any]]:
    statement = sa.select(table).where(*where)
    if order_by:
        statement = statement.order_by(*order_by)
    return [_normalize_row(row) for row in session.execute(statement).mappings().all()]


def insert_row(
    session: Session,
    table: sa.Table,
    values: Mapping[str, Any],
    errors: Mapping[str, str],
    *,
    default_error: str,
    error_type: type[Exception] = ValueError,
) -> None:
    write_with_integrity(
        session,
        lambda: session.execute(table.insert().values(**dict(values))),
        errors,
        default_error=default_error,
        error_type=error_type,
    )


def update_row(
    session: Session,
    table: sa.Table,
    values: Mapping[str, Any],
    errors: Mapping[str, str],
    *,
    default_error: str,
    error_type: type[Exception] = ValueError,
) -> int:
    primary_key = table.c.id

    def _update() -> int:
        result = session.execute(
            table.update().where(primary_key == values["id"]).values(**dict(values))
        )
        return result.rowcount or 0

    return write_with_integrity(
        session,
        _update,
        errors,
        default_error=default_error,
        error_type=error_type,
    )


def write_with_integrity(
    session: Session,
    operation: Callable[[], T],
    errors: Mapping[str, str],
    *,
    default_error: str,
    error_type: type[Exception] = ValueError,
) -> T:
    try:
        with session.begin_nested():
            return operation()
    except IntegrityError as error:
        constraint = constraint_name(error)
        code = errors.get(constraint or "", default_error)
        raise error_type(code) from error


def constraint_name(error: IntegrityError) -> str | None:
    original = error.orig
    diagnostic = getattr(original, "diag", None)
    if diagnostic is not None:
        name = getattr(diagnostic, "constraint_name", None)
        if name:
            return str(name)
    return None


def db_id(value: Any) -> str:
    return str(value).replace("-", "")


def db_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC)


def _normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _normalize_value(value) for key, value in dict(row).items()}


def _normalize_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return value.hex
    if isinstance(value, datetime):
        return db_datetime(value)
    return value
