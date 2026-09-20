#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The SQL challenge plugin must not hand the answer key to students."""

from unittest.mock import Mock, patch

from CTFd.models import UserFieldEntries, UserFields, db
from tests.helpers import create_ctfd, destroy_ctfd, gen_user, login_as_user

CHALLENGE = {
    "name": "Find Home Stadium",
    "category": "Week1",
    "description": "List every team with its stadium.",
    "value": 10,
    "state": "visible",
    "type": "sql",
    "init_query": "CREATE TABLE TEAM (TEAM_NAME VARCHAR(40)); INSERT INTO TEAM VALUES ('FC Seoul');",
    "solution_query": "SELECT TEAM_NAME FROM TEAM ORDER BY TEAM_NAME",
}


def enrolled_student(app):
    """A student who can use the API.

    The fork's registration form requires a student ID, so the account is
    created directly instead of with register_user(), and the onboarding
    plugin blocks every request until the terms are accepted.
    """
    student = gen_user(
        app.db, name="student", email="student@example.com", password="password"
    )
    for name, value in [("Student ID Number", "synthetic-1"), ("Terms of Service", True)]:
        field = UserFields.query.filter_by(name=name).first()
        db.session.add(
            UserFieldEntries(field_id=field.id, user_id=student.id, value=value)
        )
    db.session.commit()
    return login_as_user(app, name="student", password="password")


def wrong_answer():
    """A judge verdict whose reference rows the submission did not produce."""
    response = Mock(status_code=200)
    response.json.return_value = {
        "success": True,
        "match": False,
        "user_result": {"columns": ["TEAM_NAME"], "rows": [], "row_count": 0},
        "expected_result": {
            "columns": ["TEAM_NAME"],
            "rows": [["FC Seoul"]],
            "row_count": 1,
        },
    }
    return response


def attempt(client, challenge_id, is_test):
    response = client.post(
        "/api/v1/challenges/attempt",
        json={
            "challenge_id": challenge_id,
            "submission": "SELECT TEAM_NAME FROM TEAM",
            "test": is_test,
        },
    )
    return response.get_json()["data"]


def test_students_cannot_read_init_or_solution_sql():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        admin = login_as_user(app, name="admin", password="password")
        r = admin.post("/api/v1/challenges", json=CHALLENGE)
        assert r.status_code == 200, r.get_json()
        challenge_id = r.get_json()["data"]["id"]

        admin_view = admin.get(f"/api/v1/challenges/{challenge_id}").get_json()["data"]
        assert admin_view["solution_query"] == CHALLENGE["solution_query"]
        assert admin_view["init_query"] == CHALLENGE["init_query"]

        student = enrolled_student(app)
        student_view = student.get(f"/api/v1/challenges/{challenge_id}").get_json()[
            "data"
        ]
        assert student_view["name"] == CHALLENGE["name"]
        assert "solution_query" not in student_view
        assert "init_query" not in student_view
        assert "deadline" in student_view
    destroy_ctfd(app)


def test_students_never_receive_the_reference_result(monkeypatch, tmp_path):
    """A wrong Test run or Submit must not carry the expected rows back.

    The message reaches the browser, so anything in it is readable in the
    network tab even though no student view renders the reference result.
    """
    monkeypatch.setenv("SQL_JUDGE_SERVER_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("LOG_FOLDER", str(tmp_path))
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        admin = login_as_user(app, name="admin", password="password")
        r = admin.post("/api/v1/challenges", json=CHALLENGE)
        assert r.status_code == 200, r.get_json()
        challenge_id = r.get_json()["data"]["id"]
        student = enrolled_student(app)

        with patch("requests.post", return_value=wrong_answer()):
            for is_test in (True, False):
                data = attempt(student, challenge_id, is_test)
                assert data["status"] == "incorrect", data
                assert "[USER_RESULT]" in data["message"]
                assert "EXPECTED_RESULT" not in data["message"]
                assert "FC Seoul" not in data["message"]

            # Admins keep the reference rows for challenge review.
            data = attempt(admin, challenge_id, True)
            assert data["status"] == "incorrect", data
            assert "[EXPECTED_RESULT]" in data["message"]
            assert "FC Seoul" in data["message"]
    destroy_ctfd(app)
