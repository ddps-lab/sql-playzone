#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The SQL challenge plugin must not hand the answer key to students."""

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

        # The fork's registration form requires a student ID, so create the
        # student directly instead of using register_user().
        student = gen_user(
            app.db, name="student", email="student@example.com", password="password"
        )
        # the onboarding plugin blocks students until they accept the terms
        terms = UserFields.query.filter_by(name="Terms of Service").first()
        db.session.add(
            UserFieldEntries(field_id=terms.id, user_id=student.id, value=True)
        )
        db.session.commit()
        student = login_as_user(app, name="student", password="password")
        student_view = student.get(f"/api/v1/challenges/{challenge_id}").get_json()[
            "data"
        ]
        assert student_view["name"] == CHALLENGE["name"]
        assert "solution_query" not in student_view
        assert "init_query" not in student_view
        assert "deadline" in student_view
    destroy_ctfd(app)
