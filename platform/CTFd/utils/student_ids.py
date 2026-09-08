"""Validate student-number changes before account writes are flushed."""

from flask import current_app, has_app_context
from sqlalchemy import inspect, select

from CTFd.models import UserFieldEntries, UserFields

STUDENT_ID_FIELD_NAME = "Student ID Number"
DUPLICATE_MESSAGE = (
    "This student ID number is already registered to another account. "
    "Please check your ID number. If it is correct, contact your teaching assistant."
)


class StudentIDError(ValueError):
    pass


def enforce_student_ids(session, flush_context, instances):
    if not has_app_context() or not current_app.config.get("UNIQUE_STUDENT_IDS"):
        return
    changed = [
        entry
        for entry in session.new | session.dirty
        if isinstance(entry, UserFieldEntries)
        and entry not in session.deleted
        and (
            entry in session.new
            or any(
                inspect(entry).attrs[key].history.has_changes()
                for key in ("value", "field_id", "user_id")
            )
        )
    ]
    if not changed:
        return

    # One database row serializes student-number writes across workers.
    # The subsequent locking read sees commits made while this request waited.
    field_ids = (
        session.execute(
            select(UserFields.id)
            .where(UserFields.name == STUDENT_ID_FIELD_NAME)
            .order_by(UserFields.id)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    changed = [entry for entry in changed if entry.field_id in field_ids]
    if not changed:
        return
    removed_ids = {entry.id for entry in changed}
    removed_ids.update(
        entry.id for entry in session.deleted if isinstance(entry, UserFieldEntries)
    )
    rows = session.execute(
        select(UserFieldEntries.id, UserFieldEntries.user_id, UserFieldEntries.value)
        .where(UserFieldEntries.field_id.in_(field_ids))
        .with_for_update()
    ).all()
    owners = {}
    for entry_id, user_id, value in rows:
        if entry_id not in removed_ids and value is not None and str(value).strip():
            owners.setdefault(str(value).strip(), set()).add(user_id)
    for entry in changed:
        if entry.value is None:
            continue
        if not isinstance(entry.value, str):
            raise StudentIDError("Please enter your student ID number as text.")
        entry.value = entry.value.strip()
        if not entry.value:
            continue
        owner = entry.user_id if entry.user_id is not None else entry.user
        if owners.get(entry.value, set()) - {owner}:
            raise StudentIDError(DUPLICATE_MESSAGE)
        owners.setdefault(entry.value, set()).add(owner)
