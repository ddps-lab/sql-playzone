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
        path = platform / "migrations/versions/b7c1e4d2a9f3_add_login_id_to_users.py"
        spec = importlib.util.spec_from_file_location("login_id_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE users(id INTEGER PRIMARY KEY, name VARCHAR(128))")
            )
            connection.execute(
                text(
                    "INSERT INTO users VALUES (1,'admin'),(2,'Hong'),(3,'hong'),"
                    "(4,'smoke-student'),(5,NULL),(6,' spaced ')"
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
            }
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
