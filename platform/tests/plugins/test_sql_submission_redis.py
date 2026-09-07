"""Exercise the production lease against an isolated local Redis process."""

import shutil
import subprocess
import time

import pytest
from flask import Flask
from redis import Redis
from redis.exceptions import ConnectionError, LockNotOwnedError

from CTFd.cache import cache
from CTFd.plugins.sql_challenges.submissions import execution_lock


@pytest.fixture
def redis_app(tmp_path):
    executable = shutil.which("redis-server")
    if not executable:
        pytest.skip(
            "redis-server is required for the production lease integration test"
        )
    socket = str(tmp_path / "redis.sock")
    process = subprocess.Popen(
        [
            executable,
            "--port",
            "0",
            "--unixsocket",
            socket,
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        stdout=subprocess.DEVNULL,
    )
    connection = Redis(unix_socket_path=socket)
    try:
        for _ in range(100):
            try:
                if connection.ping():
                    break
            except ConnectionError:
                time.sleep(0.02)
        else:
            pytest.fail("isolated Redis did not start")
        app = Flask(__name__)
        app.config.update(
            CACHE_TYPE="redis",
            CACHE_REDIS_URL=f"unix://{socket}",
            CACHE_KEY_PREFIX="sql-test:",
        )
        cache.init_app(app)
        with app.app_context():
            yield connection
    finally:
        connection.close()
        process.terminate()
        process.wait(timeout=5)


def test_production_lease_excludes_concurrent_queries_and_preserves_successor(
    redis_app,
):
    first, second = execution_lock(1), execution_lock(1)
    assert first.acquire(blocking=False)
    assert not second.acquire(blocking=False)
    assert first.owned()
    # Expire this request's lease; another worker now owns the same key.
    redis_app.pexpire("sql-test:sql_attempt_lock_1", 0)
    assert second.acquire(blocking=False)
    assert not first.owned()
    with pytest.raises(LockNotOwnedError):
        first.release()
    assert second.owned()
    second.release()
    assert first.acquire(blocking=False)
    first.release()


def test_execution_budget_uses_prefixed_expiring_redis_key(redis_app):
    assert cache.inc("budget") == 1
    assert cache.inc("budget") == 2
    cache.expire("budget", 120)
    assert 0 < redis_app.ttl("sql-test:budget") <= 120
