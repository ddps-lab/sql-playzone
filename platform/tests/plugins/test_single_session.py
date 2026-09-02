#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A newer login signs the older session out on its very next request."""

import os

from CTFd.models import UserFieldEntries, UserFields, Users, db
from CTFd.utils.security.auth import generate_user_token
from tests.helpers import create_ctfd, destroy_ctfd, gen_user, login_as_user


def onboarded_student(app):
    student = gen_user(app.db, name="student", email="student@examplectf.com")
    for name, value in (
        ("Student ID Number", "2025000010"),
        ("Terms of Service", True),
    ):
        field = UserFields.query.filter_by(name=name).first()
        db.session.add(
            UserFieldEntries(field_id=field.id, user_id=student.id, value=value)
        )
    db.session.commit()


def test_older_session_is_signed_out_on_any_page():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        onboarded_student(app)
        first = login_as_user(app, name="student", password="password")
        # the scoreboard never loads the full user, so only a request-wide
        # check can catch the older session there
        assert first.get("/scoreboard").status_code == 200

        second = login_as_user(app, name="student", password="password")
        r = first.get("/scoreboard")
        assert r.status_code == 302
        assert "/login" in r.location
        with first.session_transaction() as sess:
            assert "id" not in sess
        assert b"signed in from another browser" in first.get("/login").data
        assert second.get("/scoreboard").status_code == 200
        assert second.get("/challenges").status_code == 200
    destroy_ctfd(app)


def test_older_session_gets_401_on_the_api():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        onboarded_student(app)
        first = login_as_user(app, name="student", password="password")
        second = login_as_user(app, name="student", password="password")
        assert first.get("/api/v1/users/me").status_code == 401
        assert second.get("/api/v1/users/me").status_code == 200
        # logging out from the older browser still works
        assert first.get("/logout").status_code == 302
    destroy_ctfd(app)


def test_api_token_requests_are_not_subject_to_the_browser_session_check():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        onboarded_student(app)
        token = generate_user_token(Users.query.filter_by(name="student").first())
        headers = {
            "Authorization": f"Token {token.value}",
            "Content-Type": "application/json",
        }
        client = app.test_client()
        # each token request logs in with a fresh nonce; none of them is rejected
        for _ in range(3):
            assert client.get("/api/v1/users/me", headers=headers).status_code == 200
    destroy_ctfd(app)


def test_a_bare_authorization_header_does_not_bypass_the_check():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        onboarded_student(app)
        first = login_as_user(app, name="student", password="password")
        login_as_user(app, name="student", password="password")
        r = first.get("/scoreboard", headers={"Authorization": "Token forged"})
        assert r.status_code == 302
        assert "/login" in r.location
    destroy_ctfd(app)


def test_concurrent_logins_leave_a_trace_in_the_logins_log():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        onboarded_student(app)
        first = login_as_user(app, name="student", password="password")
        # the logins logger writes to a file and does not propagate to caplog
        log_path = os.path.join(app.config["LOG_FOLDER"], "logins.log")
        before = os.path.getsize(log_path) if os.path.exists(log_path) else 0

        login_as_user(app, name="student", password="password")
        assert first.get("/scoreboard").status_code == 302

        with open(log_path) as log_file:
            log_file.seek(before)
            lines = log_file.read()
        assert "student login attempt while another session is active" in lines
        assert "student signed out: the account signed in from another browser" in lines
    destroy_ctfd(app)
