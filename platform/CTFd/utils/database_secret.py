"""Refresh RDS credentials on new connections, never by replaying SQL."""

import json
import os
import threading
import time

from botocore.config import Config
from pymysql.err import OperationalError
from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url


class DatabaseCredentials:
    def __init__(self, client_factory, secret_id, ttl=60):
        self.client_factory, self.secret_id, self.ttl = client_factory, secret_id, ttl
        self.value, self.expires = None, 0
        self.lock = threading.Lock()

    def get(self, force=False):
        with self.lock:
            if not force and self.value and time.monotonic() < self.expires:
                return self.value
            try:
                response = self.client_factory().get_secret_value(
                    SecretId=self.secret_id, VersionStage="AWSCURRENT"
                )
                value = json.loads(response["SecretString"])
                if not all(
                    isinstance(value.get(k), str) and value[k]
                    for k in ("username", "password")
                ):
                    raise ValueError("Invalid credential shape")
                self.value = value["username"], value["password"]
                self.expires = time.monotonic() + self.ttl
            except Exception:
                # During a Secrets Manager interruption, an existing cached
                # credential may still work. Never fall back after access denied.
                if force or self.value is None:
                    raise RuntimeError(
                        "Current database credentials are unavailable"
                    ) from None
            return self.value

    def connect(self, dialect, cargs, cparams):
        params = dict(cparams)
        params["user"], params["password"] = self.get()
        params.setdefault("connect_timeout", 5)
        try:
            return dialect.connect(*cargs, **params)
        except OperationalError as error:
            if not error.args or error.args[0] != 1045:
                raise
            params["user"], params["password"] = self.get(force=True)
            return dialect.connect(*cargs, **params)


def configure_database_secret(app):
    secret_id = app.config.get("RDS_MASTER_SECRET_ARN") or os.getenv(
        "RDS_MASTER_SECRET_ARN"
    )
    if not secret_id:
        return
    target = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    if target.drivername != "mysql+pymysql":
        raise ValueError("RDS master secret requires mysql+pymysql")
    # Recreate the SDK client after a worker fork; connection pools are per PID.
    clients = {}

    def client():
        import boto3

        pid = os.getpid()
        if pid not in clients:
            clients.clear()
            clients[pid] = boto3.client(
                "secretsmanager",
                region_name=os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION"),
                config=Config(
                    connect_timeout=2, read_timeout=2, retries={"max_attempts": 1}
                ),
            )
        return clients[pid]

    credentials = DatabaseCredentials(client, secret_id)

    def connect(dialect, record, cargs, cparams):
        if (
            dialect.name == "mysql"
            and dialect.driver == "pymysql"
            and cparams.get("host") == target.host
            and cparams.get("user") == target.username
            and int(cparams.get("port", 3306)) == (target.port or 3306)
        ):
            return credentials.connect(dialect, cargs, cparams)

    # Also covers bootstrap/database-exists and Alembic's separate engines.
    # Register before create_database(), not merely on the later ORM pool.
    event.listen(Engine, "do_connect", connect)
    app.extensions["database_secret_listener"] = connect
