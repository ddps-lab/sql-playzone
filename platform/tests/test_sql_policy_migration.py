"""Exercise the upgrade of existing SQL problems without rewriting their data."""

import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_policy_migration_preserves_existing_problem_and_marks_it_unreviewed():
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/9a21e0846b73_sql_grading_policy.py"
    )
    spec = importlib.util.spec_from_file_location("sql_policy_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()  # A fresh install creates the plugin table later.
            assert not inspect(connection).has_table("sql_challenge")
            connection.execute(
                text(
                    "CREATE TABLE sql_challenge(id INTEGER PRIMARY KEY, solution_query TEXT)"
                )
            )
            connection.execute(text("INSERT INTO sql_challenge VALUES(1, 'SELECT 42')"))
            migration.upgrade()
            row = connection.execute(
                text("SELECT solution_query, grading_policy FROM sql_challenge")
            ).one()
            assert tuple(row) == ("SELECT 42", None)
            migration.downgrade()
            assert [
                col["name"] for col in inspect(connection).get_columns("sql_challenge")
            ] == ["id", "solution_query"]
            assert (
                connection.execute(
                    text("SELECT solution_query FROM sql_challenge")
                ).scalar()
                == "SELECT 42"
            )
    engine.dispose()
