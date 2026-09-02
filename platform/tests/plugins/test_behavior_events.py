#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Behavior log: server-recorded execute events and a validated client endpoint."""

import json

from CTFd.models import UserFieldEntries, UserFields, Users, db
from tests.helpers import create_ctfd, destroy_ctfd, gen_user, login_as_user

CHALLENGE = {
    "name": "Find Home Stadium",
    "category": "Week1",
    "description": "List every team with its stadium.",
    "value": 10,
    "state": "visible",
    "type": "sql",
    "init_query": "CREATE TABLE TEAM (TEAM_NAME VARCHAR(40));",
    "solution_query": "SELECT TEAM_NAME FROM TEAM",
}


def create_app(tmp_path, monkeypatch):
    monkeypatch.delenv("LOG_FOLDER", raising=False)
    app = create_ctfd(enable_plugins=True)
    app.config["LOG_FOLDER"] = str(tmp_path)
    return app


def create_challenge(app):
    admin = login_as_user(app, name="admin", password="password")
    r = admin.post("/api/v1/challenges", json=CHALLENGE)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]["id"]


def student_client(app):
    student = gen_user(app.db, name="student", email="student@examplectf.com")
    for name, value in (
        ("Student ID Number", "2025000011"),
        ("Terms of Service", True),
    ):
        field = UserFields.query.filter_by(name=name).first()
        db.session.add(
            UserFieldEntries(field_id=field.id, user_id=student.id, value=value)
        )
    db.session.commit()
    return login_as_user(app, name="student", password="password")


def behavior_lines(tmp_path):
    path = tmp_path / "sql_challenge_behavior.log"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_test_run_records_an_execute_event_from_the_server(tmp_path, monkeypatch):
    app = create_app(tmp_path, monkeypatch)
    with app.app_context():
        challenge_id = create_challenge(app)
        client = student_client(app)
        student_id = Users.query.filter_by(name="student").first().id

        r = client.post(
            "/api/v1/challenges/attempt",
            json={"challenge_id": challenge_id, "submission": "SELECT 1", "test": True},
        )
        assert r.status_code == 200, r.get_json()
        status = r.get_json()["data"]["status"]

        events = behavior_lines(tmp_path)
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "execute"
        assert event["source"] == "server"
        assert event["user_id"] == student_id
        assert event["user_name"] == "student"
        assert event["challenge_id"] == challenge_id
        assert event["query_text"] == "SELECT 1"
        assert event["query_length"] == len("SELECT 1")
        assert event["submit_status"] == status
        assert event["session_id"] is None
        assert event["already_solved"] is False

        # once the account has solved the challenge, later Test runs say so
        from tests.helpers import gen_solve

        gen_solve(app.db, user_id=student_id, challenge_id=challenge_id)
        client.post(
            "/api/v1/challenges/attempt",
            json={"challenge_id": challenge_id, "submission": "SELECT 2", "test": True},
        )
        assert behavior_lines(tmp_path)[-1]["already_solved"] is True
    destroy_ctfd(app)


def test_client_events_are_validated_and_stamped_with_the_real_user(
    tmp_path, monkeypatch
):
    app = create_app(tmp_path, monkeypatch)
    with app.app_context():
        challenge_id = create_challenge(app)
        client = student_client(app)
        student_id = Users.query.filter_by(name="student").first().id

        base = {
            "timestamp": "2026-09-02T10:00:00Z",
            "session_id": "abc",
            "user_id": 999,
            "user_name": "somebody-else",
            "challenge_id": challenge_id,
            "challenge_name": "forged name",
            "already_solved": True,
            "typed_text": "",
            "pasted_text": "",
            "query_text": "",
        }
        events = [
            {
                **base,
                "event_type": "paste",
                "pasted_text": "SELECT 1",
                "pasted_length": 8,
            },
            {**base, "event_type": "execute"},  # only the server records execute
            {**base, "event_type": "submit", "challenge_id": 424242},
            {**base, "event_type": "focus", "typed_text": "x" * 8001},
            "not an object",
        ]
        r = client.post("/api/v1/challenges/behavior", json={"events": events})
        assert r.status_code == 200, r.get_json()
        data = r.get_json()["data"]
        assert data["logged"] == 1
        assert [d["reason"] for d in data["dropped"]] == [
            "unknown event_type",
            "unknown challenge",
            "typed_text too long",
            "not an object",
        ]

        lines = behavior_lines(tmp_path)
        assert len(lines) == 1
        assert lines[0]["event_type"] == "paste"
        assert lines[0]["user_id"] == student_id
        assert lines[0]["user_name"] == "student"
        assert lines[0]["source"] == "client"
        assert "received_at" in lines[0]
        assert lines[0]["session_id"] == "abc"
        # challenge metadata comes from the database, not the page
        assert lines[0]["challenge_name"] == CHALLENGE["name"]
        assert lines[0]["already_solved"] is False

        # already_solved is judged at the event's own time: work buffered just
        # before the first correct submission is still "before"
        from datetime import timedelta

        from tests.helpers import gen_solve

        solve = gen_solve(app.db, user_id=student_id, challenge_id=challenge_id)
        solved_at = solve.date
        stamp = lambda when: when.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        r = client.post(
            "/api/v1/challenges/behavior",
            json={
                "events": [
                    {
                        **base,
                        "event_type": "paste",
                        "timestamp": stamp(solved_at - timedelta(seconds=3)),
                    },
                    {
                        **base,
                        "event_type": "submit",
                        "timestamp": stamp(solved_at + timedelta(seconds=3)),
                    },
                    {**base, "event_type": "focus", "timestamp": "garbage"},
                ]
            },
        )
        assert r.status_code == 200, r.get_json()
        before, after, unknown = behavior_lines(tmp_path)[-3:]
        assert before["already_solved"] is False
        assert after["already_solved"] is True
        assert unknown["already_solved"] is True  # unusable timestamp: judged now

        # batch-level limits
        r = client.post("/api/v1/challenges/behavior", json={"events": []})
        assert r.status_code == 400
        r = client.post("/api/v1/challenges/behavior", json={"events": "nope"})
        assert r.status_code == 400
        # a backlog of any length is accepted: the tracker retries a rejected
        # batch forever, so a count cap would leave the page stuck
        r = client.post(
            "/api/v1/challenges/behavior",
            json={"events": [{**base, "event_type": "focus"}] * 51},
        )
        assert r.status_code == 200
        assert r.get_json()["data"]["logged"] == 51
        assert len(behavior_lines(tmp_path)) == 4 + 51

        # a full batch of the largest valid events is accepted, never 413
        big = {
            **base,
            "event_type": "paste",
            "pasted_text": "\U0001f600" * 8000,  # emoji: two \uXXXX escapes each
            "query_text": "\U0001f600" * 8000,
            "typed_text": "\U0001f600" * 8000,
        }
        r = client.post("/api/v1/challenges/behavior", json={"events": [big] * 50})
        assert r.status_code == 200
        assert r.get_json()["data"]["logged"] == 50

        # anonymous requests are refused
        assert (
            app.test_client()
            .post("/api/v1/challenges/behavior", json={"events": [base]})
            .status_code
            == 403
        )
    destroy_ctfd(app)
