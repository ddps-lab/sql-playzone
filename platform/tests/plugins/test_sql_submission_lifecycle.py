"""Admission and persistence regressions; synthetic DB, real API, mocked judge."""

import csv
import io
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from freezegun import freeze_time

from CTFd.models import Fails, Solves, UserFieldEntries, UserFields, Users, db
from CTFd.utils import get_config, set_config
from tests.helpers import create_ctfd, destroy_ctfd, gen_user, login_as_user


@pytest.fixture
def environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SQL_JUDGE_SERVER_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("LOG_FOLDER", str(tmp_path))
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        admin = login_as_user(app, name="admin", password="password")
        user = gen_user(app.db, name="student", email="student@examplectf.com")
        for name, value in [
            ("Student ID Number", "synthetic-1"),
            ("Terms of Service", True),
        ]:
            field = UserFields.query.filter_by(name=name).first()
            db.session.add(
                UserFieldEntries(field_id=field.id, user_id=user.id, value=value)
            )
        db.session.commit()
        uid = user.id
        client = login_as_user(app, name="student", password="password")

        def make(**extra):
            data = dict(
                name="Synthetic SQL",
                description="Synthetic statement",
                category="test",
                value=10,
                state="visible",
                type="sql",
                init_query="",
                solution_query="SELECT 1",
            )
            data.update(extra)
            response = admin.post("/api/v1/challenges", json=data)
            assert response.status_code == 200, response.get_json()
            return response.get_json()["data"]["id"]

        yield app, admin, client, uid, make
    destroy_ctfd(app)


def judged(**extra):
    result = {"columns": ["1"], "rows": [["1"]], "row_count": 1}
    data = dict(success=True, match=True, user_result=result, expected_result=result)
    data.update(extra)
    response = Mock(status_code=200)
    response.json.return_value = data
    return response


def submit(client, cid, **extra):
    return client.post(
        "/api/v1/challenges/attempt",
        json=dict(challenge_id=cid, submission="SELECT 1", **extra),
    )


@pytest.mark.parametrize(
    "fault", ["system", "problem", "legacy", "transport", "http", "malformed"]
)
def test_ungraded_failures_do_not_consume_the_last_attempt(environment, fault):
    _, _, client, uid, make = environment
    cid = make(max_attempts=1)
    response = judged(success=False, error="synthetic outage", error_kind=fault)
    if fault == "legacy":
        response.json.return_value.pop("error_kind")
    if fault == "http":
        response.status_code = 503
    if fault == "malformed":
        response.json.side_effect = ValueError("invalid JSON")
    import requests

    with patch(
        "requests.post",
        side_effect=(
            requests.ConnectionError("offline") if fault == "transport" else None
        ),
        return_value=response,
    ):
        result = submit(client, cid)
    assert result.get_json()["data"]["status"] == "error"
    assert Fails.query.filter_by(user_id=uid).count() == 0
    with patch("requests.post", return_value=judged()):
        retry = submit(client, cid)
    assert retry.get_json()["data"]["status"] == "correct", retry.get_json()
    assert Solves.query.filter_by(user_id=uid, challenge_id=cid).count() == 1


@pytest.mark.parametrize(
    "response",
    [
        judged(match=False),
        judged(success=False, error_kind="student_query", error="Unknown column"),
    ],
)
def test_actual_wrong_answers_consume_attempts(environment, response):
    _, _, client, uid, make = environment
    cid = make(max_attempts=1)
    with patch("requests.post", return_value=response) as judge:
        assert submit(client, cid).get_json()["data"]["status"] == "incorrect"
        assert submit(client, cid).get_json()["data"]["status"] == "ratelimited"
        assert judge.call_count == 1
    assert Fails.query.filter_by(user_id=uid).count() == 1


@pytest.mark.parametrize("match", [True, False])
def test_receipt_time_controls_storage_across_global_end(environment, match):
    _, _, client, uid, make = environment
    cid = make()
    received = datetime(2026, 9, 5, 3, 0, 0)
    set_config("end", int(received.replace(tzinfo=timezone.utc).timestamp()) + 1)
    with freeze_time(received) as clock:

        def slow_judge(*args, **kwargs):
            clock.tick(2)
            return judged(match=match)

        with patch("requests.post", side_effect=slow_judge):
            result = submit(client, cid)
    assert result.get_json()["data"]["status"] == ("correct" if match else "incorrect")
    model = Solves if match else Fails
    stored = model.query.filter_by(user_id=uid, challenge_id=cid).one()
    assert stored.date == received


@pytest.mark.parametrize("is_test", [False, True])
@pytest.mark.parametrize(
    "restriction", ["hidden", "locked", "prerequisite", "before_start", "paused"]
)
def test_access_checks_precede_sql_execution(environment, restriction, is_test):
    _, _, client, _, make = environment
    prerequisite = make()
    data = {}
    if restriction in ("hidden", "locked"):
        data["state"] = restriction
    if restriction == "prerequisite":
        data["requirements"] = {"prerequisites": [prerequisite]}
    cid = make(**data)
    if restriction == "before_start":
        set_config("start", 4102444800)
    if restriction == "paused":
        set_config("paused", True)
    with patch("requests.post", return_value=judged()) as judge:
        response = submit(client, cid, test=is_test)
        assert response.status_code in (403, 404)
        judge.assert_not_called()
    if restriction != "paused":
        page = client.get(f"/challenges/sql/{cid}")
        assert page.status_code in (403, 404)
        assert b"Synthetic statement" not in page.data


def test_after_end_viewing_does_not_accept_new_graded_submissions(environment):
    _, _, client, uid, make = environment
    cid = make()
    set_config("end", 1)
    set_config("view_after_ctf", True)
    with patch("requests.post", return_value=judged()) as judge:
        response = submit(client, cid)
        assert response.status_code == 403
        judge.assert_not_called()
    assert Solves.query.filter_by(user_id=uid).count() == 0


def test_individual_deadline_rejection_is_not_an_incorrect_answer(environment):
    _, _, client, uid, make = environment
    cid = make(deadline="2020-01-01T00:00", max_attempts=1)
    with patch("requests.post", return_value=judged()) as judge:
        response = submit(client, cid)
        assert response.get_json()["data"]["status"] == "closed"
        judge.assert_not_called()
    assert Fails.query.filter_by(user_id=uid).count() == 0


def configure_exam(admin, enabled, allowed="synthetic-1"):
    with admin.session_transaction() as session:
        nonce = session["nonce"]
    data = dict(nonce=nonce, exam_mode_allowed_ids=allowed)
    if enabled:
        data["exam_mode_enabled"] = "on"
    return admin.post("/admin/exam_mode/update", data=data)


def test_exam_roster_is_live_and_never_rewrites_bans_or_grades(environment):
    app, admin, client, uid, make = environment
    cid = make()
    banned = gen_user(app.db, name="banned", email="banned@examplectf.com", banned=True)
    banned_id = banned.id
    with patch("requests.post", return_value=judged()):
        assert submit(client, cid).get_json()["data"]["status"] == "correct"
    # Populate the existing user's session cache before changing the roster.
    assert client.get("/challenges").status_code == 200
    assert configure_exam(admin, True, "another-cohort").status_code == 302
    assert client.get("/challenges").status_code == 403
    assert Users.query.get(uid).banned is False
    assert Users.query.get(banned_id).banned is True
    rows = list(
        csv.DictReader(
            io.StringIO(
                admin.get("/admin/submission_export/export.csv")
                .get_data(as_text=True)
                .lstrip("\ufeff")
            )
        )
    )
    assert next(row for row in rows if row["Name"] == "student")["Total Score"] == "10"
    assert configure_exam(admin, True).status_code == 302
    assert client.get("/challenges").status_code == 200
    assert configure_exam(admin, False).status_code == 302
    assert Users.query.get(banned_id).banned is True
    assert client.get("/healthcheck").status_code == 200


def test_exam_requires_a_valid_roster_before_changing_configuration(environment):
    _, admin, _, _, _ = environment
    assert configure_exam(admin, True, "").status_code == 400
    assert not get_config("exam_mode_enabled")


def test_export_includes_banned_and_hidden_students_with_status(environment):
    app, admin, _, uid, make = environment
    user = Users.query.get(uid)
    user.banned = True
    user.hidden = True
    db.session.commit()
    rows = list(
        csv.DictReader(
            io.StringIO(
                admin.get("/admin/submission_export/export.csv")
                .get_data(as_text=True)
                .lstrip("\ufeff")
            )
        )
    )
    row = next(row for row in rows if row["Name"] == "student")
    assert row["Banned"] == "True"
    assert row["Hidden"] == "True"


def test_invalid_deadline_keeps_previous_settings(environment):
    _, admin, _, _, make = environment
    cid = make(deadline="2026-09-05T12:00")
    before = admin.get(f"/api/v1/challenges/{cid}").get_json()["data"]
    result = admin.patch(
        f"/api/v1/challenges/{cid}", json={"deadline": "not-a-time", "value": 999}
    )
    assert result.status_code == 400
    after = admin.get(f"/api/v1/challenges/{cid}").get_json()["data"]
    assert (after["deadline"], after["value"]) == (before["deadline"], before["value"])


def test_test_runs_never_store_grades_or_use_max_attempts(environment):
    _, _, client, uid, make = environment
    cid = make(max_attempts=1)
    with patch("requests.post", return_value=judged(match=False)):
        for _ in range(2):
            assert (
                submit(client, cid, test=True).get_json()["data"]["status"]
                == "incorrect"
            )
    assert Fails.query.filter_by(user_id=uid).count() == 0
    with patch("requests.post", return_value=judged()):
        assert submit(client, cid).get_json()["data"]["status"] == "correct"


def test_test_and_submit_share_account_lock_and_release_on_error(environment):
    from CTFd.cache import cache

    _, _, client, uid, make = environment
    first, second = make(), make()
    key = f"sql_attempt_lock_{uid}"
    cache.add(key, 1, timeout=30)
    with patch("requests.post", return_value=judged()) as judge:
        for cid, mode in [(first, True), (second, False)]:
            assert (
                submit(client, cid, test=mode).get_json()["data"]["status"]
                == "ratelimited"
            )
        judge.assert_not_called()
    cache.delete(key)
    with patch(
        "requests.post", return_value=judged(success=False, error_kind="system")
    ):
        assert submit(client, first).get_json()["data"]["status"] == "error"
    assert cache.get(key) is None


def test_execution_throttle_does_not_use_the_wrong_answer_budget(environment):
    from CTFd.cache import cache

    _, _, client, uid, make = environment
    cid = make()
    with freeze_time("2026-09-05T03:00:00Z"):
        key = f"sql_execution_budget_{uid}_{int(datetime.utcnow().timestamp()) // 60}"
        cache.set(key, 59, timeout=120)
        with patch("requests.post", return_value=judged()) as judge:
            assert (
                submit(client, cid, test=True).get_json()["data"]["status"] == "correct"
            )
            assert (
                submit(client, cid, test=True).get_json()["data"]["status"]
                == "ratelimited"
            )
            assert judge.call_count == 1
    assert Fails.query.filter_by(user_id=uid).count() == 0


def test_storage_failure_never_acknowledges_a_saved_correct_answer(environment):
    from sqlalchemy.exc import SQLAlchemyError
    from CTFd.plugins.sql_challenges import SQLChallengeType

    _, _, client, uid, make = environment
    cid = make()
    with patch("requests.post", return_value=judged()), patch.object(
        SQLChallengeType, "solve", side_effect=SQLAlchemyError("storage unavailable")
    ):
        result = submit(client, cid)
    assert result.status_code == 503
    assert result.get_json()["data"]["status"] == "error"
    assert Solves.query.filter_by(user_id=uid).count() == 0
    with patch("requests.post", return_value=judged()):
        assert submit(client, cid).get_json()["data"]["status"] == "correct"


def test_wrong_attempt_timeout_and_solved_retries(environment):
    _, _, client, uid, make = environment
    cid = make(max_attempts=1)
    set_config("max_attempts_behavior", "timeout")
    set_config("max_attempts_timeout", 30)
    with freeze_time("2026-09-05T03:00:00Z") as clock:
        with patch("requests.post", return_value=judged(match=False)):
            assert submit(client, cid).get_json()["data"]["status"] == "incorrect"
            assert submit(client, cid).get_json()["data"]["status"] == "ratelimited"
        clock.tick(31)
        with patch("requests.post", return_value=judged()):
            assert submit(client, cid).get_json()["data"]["status"] == "correct"
            assert submit(client, cid).get_json()["data"]["status"] == "already_solved"
    assert Solves.query.filter_by(user_id=uid).count() == 1


def test_exam_roster_covers_users_created_after_enabling(environment):
    app, admin, _, _, _ = environment
    configure_exam(admin, True)
    user = gen_user(app.db, name="late", email="late@examplectf.com")
    uid = user.id
    for name, value in [
        ("Student ID Number", "not-allowed"),
        ("Terms of Service", True),
    ]:
        field = UserFields.query.filter_by(name=name).first()
        db.session.add(UserFieldEntries(field_id=field.id, user_id=uid, value=value))
    db.session.commit()
    client = login_as_user(app, name="late", password="password")
    assert client.get("/api/v1/challenges").status_code == 403
    assert admin.get("/admin/exam_mode/").status_code == 200
    assert app.test_client().get("/healthcheck").status_code == 200


def test_invalid_exam_roster_preserves_previous_configuration(environment):
    _, admin, client, _, _ = environment
    configure_exam(admin, True)
    assert configure_exam(admin, True, "").status_code == 400
    assert get_config("exam_mode_enabled") is True
    assert get_config("exam_mode_allowed_ids") == "synthetic-1"
    assert client.get("/challenges").status_code == 200


def test_expired_execution_cannot_save_or_release_a_successor_lock(environment):
    from CTFd.cache import cache

    _, _, client, uid, make = environment
    cid = make()
    key = f"sql_attempt_lock_{uid}"
    with freeze_time("2026-09-05T03:00:00Z") as clock:

        def delayed(*args, **kwargs):
            clock.tick(31)
            assert cache.get(key) is None
            # Redis expires keys eagerly; SimpleCache retains expired entries.
            cache.set(key, "successor", timeout=30)
            return judged()

        with patch("requests.post", side_effect=delayed):
            result = submit(client, cid)
        assert result.get_json()["data"]["status"] == "error"
        assert cache.get(key) == "successor"
    assert Solves.query.filter_by(user_id=uid).count() == 0


def test_sql_page_serves_the_manifest_bundle(environment):
    import json
    from pathlib import Path

    _, _, client, _, make = environment
    cid = make()
    manifest = (
        Path(__file__).resolve().parents[2] / "CTFd/themes/ddps/static/manifest.json"
    )
    asset = json.loads(manifest.read_text())["assets/js/sql_challenge.js"]["file"]
    page = client.get(f"/challenges/sql/{cid}")
    assert page.status_code == 200
    assert asset.encode() in page.data
    script = client.get("/themes/ddps/static/" + asset)
    assert script.status_code == 200
    assert b"The server could not confirm the result." in script.data
