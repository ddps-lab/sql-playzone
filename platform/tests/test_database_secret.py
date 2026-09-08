from unittest.mock import Mock
import pytest
from pymysql.err import OperationalError
from CTFd.utils.database_secret import DatabaseCredentials


def test_rotation_refreshes_only_failed_connection_and_never_mutates_static_params():
    client = Mock()
    client.get_secret_value.side_effect = [
        {"SecretString": '{"username":"synthetic","password":"old"}'},
        {"SecretString": '{"username":"synthetic","password":"new"}'},
    ]
    credentials = DatabaseCredentials(lambda: client, "synthetic-secret")
    dialect = Mock()
    dialect.connect.side_effect = [
        OperationalError(1045, "Access denied"),
        "connection",
    ]
    params = {"host": "test", "password": "boot", "user": "synthetic"}
    assert credentials.connect(dialect, [], params) == "connection"
    assert [call.kwargs["password"] for call in dialect.connect.call_args_list] == [
        "old",
        "new",
    ]
    assert params["password"] == "boot"
    assert client.get_secret_value.call_count == 2
    assert client.get_secret_value.call_args.kwargs["VersionStage"] == "AWSCURRENT"


def test_unrelated_connection_failure_is_not_retried():
    client = Mock()
    client.get_secret_value.return_value = {
        "SecretString": '{"username":"u","password":"p"}'
    }
    credentials = DatabaseCredentials(lambda: client, "test")
    dialect = Mock()
    dialect.connect.side_effect = OperationalError(2003, "Cannot connect")
    with pytest.raises(OperationalError):
        credentials.connect(dialect, [], {})
    assert dialect.connect.call_count == 1


def test_secret_outage_can_use_cache_but_cannot_hide_failed_forced_refresh():
    client = Mock()
    client.get_secret_value.side_effect = [
        {"SecretString": '{"username":"u","password":"p"}'},
        RuntimeError("outage"),
        RuntimeError("outage"),
    ]
    credentials = DatabaseCredentials(lambda: client, "test", ttl=0)
    assert credentials.get() == ("u", "p")
    assert credentials.get() == ("u", "p")
    with pytest.raises(RuntimeError, match="credentials are unavailable"):
        credentials.get(force=True)


def test_retry_is_bounded_even_when_current_secret_is_not_accepted():
    client = Mock()
    client.get_secret_value.return_value = {
        "SecretString": '{"username":"u","password":"p"}'
    }
    credentials = DatabaseCredentials(lambda: client, "test")
    dialect = Mock()
    dialect.connect.side_effect = OperationalError(1045, "Access denied")
    with pytest.raises(OperationalError):
        credentials.connect(dialect, [], {})
    assert dialect.connect.call_count == 2


def test_real_engine_reconnects_after_password_rotation(monkeypatch):
    """Opt-in synthetic MySQL integration; never uses an application database."""
    import os
    from flask import Flask
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.engine import Engine, make_url
    from sqlalchemy.pool import NullPool
    from CTFd.utils.database_secret import configure_database_secret

    url = os.getenv("SQL_ROTATION_TEST_URL")
    if not url:
        pytest.skip("requires isolated synthetic MySQL")
    root = create_engine(url, poolclass=NullPool)
    with root.begin() as connection:
        connection.execute(
            text("CREATE USER 'rotation_synthetic'@'%' IDENTIFIED BY 'synthetic-old'")
        )
    target = make_url(url).set(
        username="rotation_synthetic", password="static-boot-value", database=None
    )
    target = target._replace(database=None)
    app = Flask("rotation-test")
    app.config.update(
        RDS_MASTER_SECRET_ARN="synthetic-secret",
        SQLALCHEMY_DATABASE_URI=target.render_as_string(hide_password=False),
    )
    client = Mock()
    client.get_secret_value.side_effect = [
        {
            "SecretString": '{"username":"rotation_synthetic","password":"synthetic-old"}'
        },
        {
            "SecretString": '{"username":"rotation_synthetic","password":"synthetic-new"}'
        },
    ]
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: client)
    configure_database_secret(app)
    engine = create_engine(target, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 41 + 1")).scalar() == 42
        with root.begin() as connection:
            connection.execute(
                text(
                    "ALTER USER 'rotation_synthetic'@'%' IDENTIFIED BY 'synthetic-new'"
                )
            )
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 42 + 1")).scalar() == 43
        assert client.get_secret_value.call_count == 2
    finally:
        event.remove(Engine, "do_connect", app.extensions["database_secret_listener"])
        engine.dispose()
        with root.begin() as connection:
            connection.execute(text("DROP USER 'rotation_synthetic'@'%'"))
        root.dispose()
