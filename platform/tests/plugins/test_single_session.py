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


def test_logging_out_of_the_newer_session_does_not_revive_the_older_one():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        onboarded_student(app)
        first = login_as_user(app, name="student", password="password")
        second = login_as_user(app, name="student", password="password")
        assert second.get("/logout").status_code == 302
        r = first.get("/scoreboard")
        assert r.status_code == 302
        assert "/login" in r.location
    destroy_ctfd(app)


CHROME = "Mozilla/5.0 (Macintosh) Chrome/124.0 Safari/537.36"
FIREFOX = "Mozilla/5.0 (X11; Linux x86_64) Firefox/128.0"


def new_login_lines(app, log_path, before):
    # every create_ctfd() adds another file handler to the shared logger, so
    # the same line is written several times: compare unique lines
    with open(log_path) as log_file:
        log_file.seek(before)
        lines = [
            line for line in log_file.read().splitlines() if "logged in via" in line
        ]
    return sorted(set(lines), key=lines.index)


def test_every_login_is_logged_with_its_browser_and_the_previous_login():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        onboarded_student(app)
        log_path = os.path.join(app.config["LOG_FOLDER"], "logins.log")
        before = os.path.getsize(log_path) if os.path.exists(log_path) else 0

        client = app.test_client()
        client.environ_base["HTTP_USER_AGENT"] = CHROME
        client.get("/login")
        with client.session_transaction() as sess:
            nonce = sess["nonce"]
        r = client.post(
            "/login", data={"name": "student", "password": "password", "nonce": nonce}
        )
        assert r.status_code == 302
        lines = new_login_lines(app, log_path, before)
        assert len(lines) == 1
        assert (
            "student logged in via form (Mozilla/5.0 (Macintosh) Chrome/124.0 Safari/537.36); first login on record"
            in lines[0]
        )

        # a second login from another browser names the previous one
        other = app.test_client()
        other.environ_base["HTTP_USER_AGENT"] = FIREFOX
        other.get("/login")
        with other.session_transaction() as sess:
            nonce = sess["nonce"]
        r = other.post(
            "/login", data={"name": "student", "password": "password", "nonce": nonce}
        )
        assert r.status_code == 302
        lines = new_login_lines(app, log_path, before)
        assert len(lines) == 2
        assert (
            "student logged in via form (Mozilla/5.0 (X11; Linux x86_64) Firefox/128.0); previous login 0 min ago from 127.0.0.1 (Mozilla/5.0 (Macintosh) Chrome/124.0 Safari/537.36)"
            in lines[1]
        )

        # a wrong password logs nothing here
        with other.session_transaction() as sess:
            nonce = sess["nonce"]
        other.post(
            "/login", data={"name": "student", "password": "wrong", "nonce": nonce}
        )
        assert len(new_login_lines(app, log_path, before)) == 2

        # API token requests are not logins of a browser session
        token = generate_user_token(Users.query.filter_by(name="student").first())
        headers = {
            "Authorization": f"Token {token.value}",
            "Content-Type": "application/json",
        }
        assert (
            app.test_client().get("/api/v1/users/me", headers=headers).status_code
            == 200
        )
        assert len(new_login_lines(app, log_path, before)) == 2
    destroy_ctfd(app)


def test_a_refused_login_is_not_logged_as_a_login():
    from CTFd.utils import set_config

    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        onboarded_student(app)
        log_path = os.path.join(app.config["LOG_FOLDER"], "logins.log")
        client = login_as_user(app, name="student", password="password")
        set_config("exam_browser_required", "true")
        before = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        # an authenticated session re-posting the login form from a normal
        # browser during the exam is refused by the exam-browser rule first
        with client.session_transaction() as sess:
            nonce = sess["nonce"]
        client.environ_base["HTTP_USER_AGENT"] = CHROME
        r = client.post(
            "/login", data={"name": "student", "password": "password", "nonce": nonce}
        )
        assert r.status_code == 403
        assert new_login_lines(app, log_path, before) == []
    destroy_ctfd(app)


def test_admins_may_be_signed_in_from_several_places():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        first = login_as_user(app, name="admin", password="password")
        second = login_as_user(app, name="admin", password="password")
        # neither session is signed out, on pages or on the API
        assert first.get("/scoreboard").status_code == 200
        assert first.get("/api/v1/users/me").status_code == 200
        assert first.get("/admin/users").status_code == 200
        assert second.get("/admin/users").status_code == 200
        # a token request beside the browser does not sign the browser out
        token = generate_user_token(Users.query.filter_by(name="admin").first())
        headers = {
            "Authorization": f"Token {token.value}",
            "Content-Type": "application/json",
        }
        assert (
            app.test_client().get("/api/v1/users/me", headers=headers).status_code
            == 200
        )
        assert first.get("/challenges").status_code == 200
    destroy_ctfd(app)
