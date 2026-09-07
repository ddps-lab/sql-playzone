"""Run the MySQL-specific plugin migration chain after the core schema phase."""

import importlib.util
import os
import secrets
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def test_fresh_mysql_plugin_migrations_include_policy_and_preserve_existing_values():
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
        path = platform / "migrations/versions/9a21e0846b73_sql_grading_policy.py"
        spec = importlib.util.spec_from_file_location("core_policy_migration", path)
        core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(core)
        migrations = platform / "CTFd/plugins/sql_challenges/migrations"
        config = Config()
        config.set_main_option("script_location", str(migrations))
        config.set_main_option("version_locations", str(migrations))
        script = ScriptDirectory.from_config(config)
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            op = Operations(context)
            with Operations.context(context):
                core.upgrade()
            connection.execute(text("CREATE TABLE challenges(id INTEGER PRIMARY KEY)"))
            for revision in reversed(
                list(script.iterate_revisions(script.get_current_head(), None))
            ):
                with context.begin_transaction():
                    revision.module.upgrade(op=op)
            assert "grading_policy" in {
                col["name"] for col in inspect(connection).get_columns("sql_challenge")
            }
            connection.execute(text("INSERT INTO challenges VALUES(1)"))
            connection.execute(
                text(
                    "INSERT INTO sql_challenge(id,solution_query,grading_policy) VALUES(1,'SELECT 42',JSON_OBJECT('version',1))"
                )
            )
            script.get_revision(script.get_current_head()).module.upgrade(op=op)
            assert connection.execute(
                text(
                    "SELECT solution_query, JSON_EXTRACT(grading_policy,'$.version') FROM sql_challenge"
                )
            ).one() == ("SELECT 42", "1")
    finally:
        engine.dispose()
        with root.begin() as connection:
            connection.execute(text(f"DROP DATABASE `{database}`"))
        root.dispose()
