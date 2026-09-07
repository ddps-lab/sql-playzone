"""The login ID migration backfills unique names and makes the column unique."""

import importlib.util
import os
import secrets
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError


def load_migration(platform, filename):
    path = platform / "migrations/versions" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_login_id_migration_backfills_unique_names_only():
    uri = os.getenv("SQL_MIGRATION_TEST_URL")
    if not uri:
        pytest.skip("requires isolated synthetic MySQL")
    root = create_engine(uri)
    database = "migration_synthetic_" + secrets.token_hex(6)
    with root.begin() as connection:
        connection.execute(text(f"CREATE DATABASE `{database}`"))
    engine = create_engine(make_url(uri).set(database=database))
    try:
        platform = Path(__file__).resolve().parents[1]
        migration = load_migration(platform, "b7c1e4d2a9f3_add_login_id_to_users.py")
        follow_up = load_migration(
            platform, "d4e5f6a7b8c9_clear_login_id_of_passwordless_accounts.py"
        )
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE users(id INTEGER PRIMARY KEY, name VARCHAR(128),"
                    " password VARCHAR(128))"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO users VALUES (1,'admin','h'),(2,'Hong','h'),(3,'hong','h'),"
                    "(4,'smoke-student','h'),(5,NULL,'h'),(6,' spaced ','h'),"
                    "(7,'Google Only',NULL)"
                )
            )
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                with context.begin_transaction():
                    migration.upgrade()
            rows = dict(
                connection.execute(
                    text("SELECT id, login_id FROM users ORDER BY id")
                ).all()
            )
            assert rows == {
                1: "admin",
                2: None,  # case variants are ambiguous in MySQL and stay empty
                3: None,
                4: "smoke-student",
                5: None,
                6: "spaced",
                7: None,  # no password: never logged in by name, chooses an ID later
            }
            # a database migrated by the earlier, broader copy: the follow-up
            # clears only password-less accounts whose ID is their name
            connection.execute(
                text("UPDATE users SET login_id = 'Google Only' WHERE id = 7")
            )
            with Operations.context(context):
                with context.begin_transaction():
                    follow_up.upgrade()
            rows = dict(
                connection.execute(
                    text("SELECT id, login_id FROM users ORDER BY id")
                ).all()
            )
            assert rows[7] is None
            assert rows[1] == "admin" and rows[4] == "smoke-student"
            indexes = {i["name"]: i for i in inspect(connection).get_indexes("users")}
            assert indexes["ix_users_login_id"]["unique"]
            with pytest.raises(IntegrityError):
                connection.execute(
                    text("INSERT INTO users(id, name, login_id) VALUES (7,'x','ADMIN')")
                )
    finally:
        engine.dispose()
        with root.begin() as connection:
            connection.execute(text(f"DROP DATABASE `{database}`"))
        root.dispose()
