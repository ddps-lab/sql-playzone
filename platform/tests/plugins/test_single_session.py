#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A newer login signs the older session out on its very next request."""

import json
import os
import re

from CTFd.models import UserFieldEntries, UserFields, Users, db
from CTFd.utils.security.auth import generate_user_token
from tests.helpers import create_ctfd, destroy_ctfd, gen_user, login_as_user


def enable_single_session():
    from CTFd.utils import set_config

    set_config("single_session_required", "true")


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
        enable_single_session()
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
        enable_single_session()
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
        enable_single_session()
        # tokens are for admins (the onboarding plugin refuses student tokens)
        token = generate_user_token(Users.query.filter_by(name="admin").first())
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
        enable_single_session()
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
        enable_single_session()
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
            line
            for line in log_file.read().splitlines()
            if re.match(
                r"^\[[^\]]+\] \S+ - event=session_started user_id=[0-9]+ login_id=",
                line,
            )
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
            '"student" session started via form ("Mozilla/5.0 (Macintosh) Chrome/124.0 Safari/537.36"); first session on record'
            in lines[0]
        )
        student_id = Users.query.filter_by(login_id="student").one().id
        assert f'user_id={student_id} login_id="student"' in lines[0]

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
            '"student" session started via form ("Mozilla/5.0 (X11; Linux x86_64) Firefox/128.0"); previous session 0 min ago from 127.0.0.1 ("Mozilla/5.0 (Macintosh) Chrome/124.0 Safari/537.36")'
            in lines[1]
        )
        assert f'user_id={student_id} login_id="student"' in lines[1]

        # a wrong password logs nothing here
        with other.session_transaction() as sess:
            nonce = sess["nonce"]
        other.post(
            "/login", data={"name": "student", "password": "wrong", "nonce": nonce}
        )
        assert len(new_login_lines(app, log_path, before)) == 2

        # API token requests (admins only) are not logins of a browser session
        token = generate_user_token(Users.query.filter_by(name="admin").first())
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


def test_registration_is_logged_as_the_first_session():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        log_path = os.path.join(app.config["LOG_FOLDER"], "logins.log")
        before = os.path.getsize(log_path) if os.path.exists(log_path) else 0

        client = app.test_client()
        client.environ_base["HTTP_USER_AGENT"] = CHROME
        client.get("/register")
        with client.session_transaction() as sess:
            nonce = sess["nonce"]
        data = {
            "name": "newcomer",
            "email": "newcomer@examplectf.com",
            "password": "password",
            "nonce": nonce,
        }
        for field in UserFields.query.all():
            # the registration form requires the student fields
            data[f"fields[{field.id}]"] = "2025000011" if "ID" in field.name else "true"
        r = client.post("/register", data=data)
        assert r.status_code == 302
        with client.session_transaction() as sess:
            assert "id" in sess
        lines = new_login_lines(app, log_path, before)
        assert len(lines) == 1
        assert '"newcomer" session started via registration (' in lines[0]
        user_id = Users.query.filter_by(login_id="newcomer").one().id
        assert f'user_id={user_id} login_id="newcomer"' in lines[0]
        assert "first session on record" in lines[0]

        # the next login names the registration as the previous session
        other = app.test_client()
        other.environ_base["HTTP_USER_AGENT"] = FIREFOX
        other.get("/login")
        with other.session_transaction() as sess:
            nonce = sess["nonce"]
        r = other.post(
            "/login",
            data={"name": "newcomer", "password": "password", "nonce": nonce},
        )
        assert r.status_code == 302
        lines = new_login_lines(app, log_path, before)
        assert len(lines) == 2
        assert "previous session 0 min ago from 127.0.0.1" in lines[1]
    destroy_ctfd(app)


def test_same_names_and_email_logins_use_the_authenticated_account_identity():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        first_id = gen_user(
            db, name="김민수", email="first@examplectf.com", login_id="first"
        ).id
        second_id = gen_user(
            db, name="김민수", email="second@examplectf.com", login_id="second"
        ).id
        log_path = os.path.join(app.config["LOG_FOLDER"], "logins.log")
        before = os.path.getsize(log_path) if os.path.exists(log_path) else 0

        client = app.test_client()
        client.get("/login")
        with client.session_transaction() as sess:
            nonce = sess["nonce"]
        assert (
            client.post(
                "/login",
                data={
                    "name": "first@examplectf.com",
                    "password": "password",
                    "nonce": nonce,
                    "user_id": second_id,
                    "login_id": "forged",
                },
            ).status_code
            == 302
        )
        login_as_user(app, name="second")
        lines = new_login_lines(app, log_path, before)
        assert len(lines) == 2
        assert f'user_id={first_id} login_id="first" "김민수"' in lines[0]
        assert f'user_id={second_id} login_id="second" "김민수"' in lines[1]
        assert all("first session on record" in line for line in lines)

        # A changed display name or login ID still belongs to the same account.
        first = db.session.get(Users, first_id)
        first.name = "김민수 (수정)"
        first.login_id = "renamed"
        db.session.commit()
        login_as_user(app, name="renamed")
        lines = new_login_lines(app, log_path, before)
        assert len(lines) == 3
        assert f'user_id={first_id} login_id="renamed" "김민수 (수정)"' in lines[-1]
        assert "previous session" in lines[-1]

        # The core success log carries the same identifiers as the session log.
        with open(log_path) as log_file:
            log_file.seek(before)
            core_lines = [line for line in log_file if " logged in" in line]
        for user_id, login_id in (
            (first_id, "first"),
            (second_id, "second"),
            (first_id, "renamed"),
        ):
            assert any(
                f'user_id={user_id} login_id="{login_id}"' in line
                for line in core_lines
            )
        assert all('login_id="forged"' not in line for line in core_lines)
    destroy_ctfd(app)


def test_first_google_login_has_a_user_id_before_a_login_id_is_chosen():
    from tests.oauth.test_google import google_callback, google_userinfo

    app = create_ctfd(enable_plugins=True)
    app.config["GOOGLE_CLIENT_ID"] = "client"
    app.config["GOOGLE_CLIENT_SECRET"] = "secret"
    with app.app_context():
        log_path = os.path.join(app.config["LOG_FOLDER"], "logins.log")
        before = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        client = app.test_client()
        assert (
            google_callback(client, google_userinfo("new@hanyang.ac.kr")).status_code
            == 302
        )
        user = Users.query.filter_by(email="new@hanyang.ac.kr").one()
        assert user.login_id is None
        identity = f"user_id={user.id} login_id=null"
        lines = new_login_lines(app, log_path, before)
        assert len(lines) == 1
        assert identity in lines[0]
        assert "session started via google" in lines[0]
        with open(log_path) as log_file:
            log_file.seek(before)
            assert any(
                identity in line and "logged in via Google OAuth" in line
                for line in log_file
            )
    destroy_ctfd(app)


def test_display_name_cannot_split_a_login_record_into_extra_lines():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        name = '김민수\nuser_id=999 login_id="forged" session started via form'
        user_id = gen_user(
            db, name=name, email="quoted@examplectf.com", login_id="quoted"
        ).id
        log_path = os.path.join(app.config["LOG_FOLDER"], "logins.log")
        before = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        login_as_user(app, name="quoted")
        lines = new_login_lines(app, log_path, before)
        assert len(lines) == 1
        assert (
            f'user_id={user_id} login_id="quoted" {json.dumps(name, ensure_ascii=False)}'
            in lines[0]
        )
        with open(log_path) as log_file:
            log_file.seek(before)
            assert all(
                f'user_id={user_id} login_id="quoted" ' in line and " - event=" in line
                for line in log_file
            )
    destroy_ctfd(app)


def test_login_and_test_execution_can_be_joined_by_user_id():
    from CTFd.api.v1.challenges import behavior_log_path, record_execute_event
    from CTFd.models import Challenges
    from tests.helpers import gen_challenge

    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        onboarded_student(app)
        challenge_id = gen_challenge(db).id
        log_path = os.path.join(app.config["LOG_FOLDER"], "logins.log")
        before = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        client = login_as_user(app, name="student")
        with client:
            assert client.get("/settings").status_code == 200
            challenge = db.session.get(Challenges, challenge_id)
            record_execute_event(challenge, "SELECT 1", "correct", "Correct")
        event = json.loads(behavior_log_path().read_text().splitlines()[-1])
        assert event["event_type"] == "execute"
        identity = f'user_id={event["user_id"]} login_id="student"'
        lines = new_login_lines(app, log_path, before)
        assert len(lines) == 1
        assert f" - event=session_started {identity} " in lines[0]
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
        enable_single_session()
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


def test_students_keep_both_sessions_while_the_switch_is_off():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        onboarded_student(app)
        first = login_as_user(app, name="student", password="password")
        second = login_as_user(app, name="student", password="password")
        assert first.get("/scoreboard").status_code == 200
        assert first.get("/challenges").status_code == 200
        assert first.get("/api/v1/users/me").status_code == 200
        assert second.get("/challenges").status_code == 200
    destroy_ctfd(app)
