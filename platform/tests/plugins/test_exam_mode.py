#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Exam browser restriction: students must use the lockdown browser when enabled."""

from CTFd.models import SolutionFiles, UserFieldEntries, UserFields, Users, db
from CTFd.utils import get_config, set_config
from tests.helpers import (
    create_ctfd,
    destroy_ctfd,
    gen_challenge,
    gen_file,
    gen_solution,
    gen_user,
    login_as_user,
)

TRUSTLOCK = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Trustlockbrowser/2.1.1 Chrome/124.0.6367.207 Safari/537.36 CMAC 1.0001;"
)
CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.6367.207 Safari/537.36"
)


def student_client(app):
    student = gen_user(app.db, name="student", email="student@examplectf.com")
    # a student who finished onboarding: student ID and consent recorded
    for name, value in (
        ("Student ID Number", "2025000009"),
        ("Terms of Service", True),
    ):
        field = UserFields.query.filter_by(name=name).first()
        db.session.add(
            UserFieldEntries(field_id=field.id, user_id=student.id, value=value)
        )
    db.session.commit()
    return login_as_user(app, name="student", password="password")


def test_admin_toggles_the_exam_browser_requirement_without_touching_bans():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        gen_user(app.db, name="banned", email="banned@examplectf.com", banned=True)
        admin = login_as_user(app, name="admin", password="password")
        r = admin.get("/admin/exam_mode/")
        assert r.status_code == 200
        assert b"Allow the exam browser only" in r.data
        with admin.session_transaction() as sess:
            nonce = sess["nonce"]

        r = admin.post(
            "/admin/exam_mode/browser",
            data={
                "exam_browser_required": "on",
                "exam_browser_marker": " Trustlockbrowser ",
                "nonce": nonce,
            },
        )
        assert r.status_code == 302
        assert get_config("exam_browser_required") is True
        assert get_config("exam_browser_marker") == "Trustlockbrowser"
        assert Users.query.filter_by(banned=True).count() == 1

        r = admin.post(
            "/admin/exam_mode/browser", data={"exam_browser_marker": "", "nonce": nonce}
        )
        assert r.status_code == 302
        assert get_config("exam_browser_required") is False
        assert get_config("exam_browser_marker") == "Trustlockbrowser"
        assert Users.query.filter_by(banned=True).count() == 1
    destroy_ctfd(app)


def test_students_need_the_exam_browser_when_required():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        client = student_client(app)
        assert (
            client.get("/challenges", headers={"User-Agent": CHROME}).status_code == 200
        )

        set_config("exam_browser_required", "true")

        r = client.get("/challenges", headers={"User-Agent": CHROME})
        assert r.status_code == 403
        assert "Trustlock".encode() in r.data
        r = client.get("/api/v1/users/me", headers={"User-Agent": CHROME})
        assert r.status_code == 403
        assert r.get_json()["success"] is False

        assert (
            client.get("/challenges", headers={"User-Agent": TRUSTLOCK}).status_code
            == 200
        )
        assert (
            client.get(
                "/api/v1/users/me", headers={"User-Agent": TRUSTLOCK}
            ).status_code
            == 200
        )
        # logging out is always possible
        assert client.get("/logout", headers={"User-Agent": CHROME}).status_code == 302

        set_config("exam_browser_required", "false")
        client = login_as_user(app, name="student", password="password")
        assert (
            client.get("/challenges", headers={"User-Agent": CHROME}).status_code == 200
        )
    destroy_ctfd(app)


def test_admins_and_the_login_page_are_not_restricted():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        set_config("exam_browser_required", "true")
        anonymous = app.test_client()
        assert (
            anonymous.get("/login", headers={"User-Agent": CHROME}).status_code == 200
        )
        # password recovery must work from a normal browser too
        assert (
            anonymous.get("/reset_password", headers={"User-Agent": CHROME}).status_code
            == 200
        )
        assert (
            anonymous.get("/healthcheck", headers={"User-Agent": ""}).status_code == 200
        )
        assert anonymous.get("/", headers={"User-Agent": CHROME}).status_code == 403

        admin = login_as_user(app, name="admin", password="password")
        assert (
            admin.get("/challenges", headers={"User-Agent": CHROME}).status_code == 200
        )
        assert (
            admin.get("/admin/exam_mode/", headers={"User-Agent": CHROME}).status_code
            == 200
        )
    destroy_ctfd(app)


def test_challenge_attachments_need_the_exam_browser_but_site_assets_do_not():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        challenge_id = gen_challenge(app.db).id
        gen_file(app.db, location="attachments/answers.txt", challenge_id=challenge_id)
        gen_file(app.db, location="branding/logo.png")  # a standard upload
        client = student_client(app)
        set_config("exam_browser_required", "true")

        r = client.get("/files/attachments/answers.txt", headers={"User-Agent": CHROME})
        assert r.status_code == 403
        r = client.get(
            "/files/attachments/answers.txt", headers={"User-Agent": TRUSTLOCK}
        )
        assert r.status_code != 403
        r = client.get("/files/branding/logo.png", headers={"User-Agent": CHROME})
        assert r.status_code != 403

        # solution attachments are course material too
        solution = gen_solution(app.db, challenge_id=challenge_id, state="visible")
        db.session.add(
            SolutionFiles(location="solutions/answer.sql", solution_id=solution.id)
        )
        db.session.commit()
        r = client.get("/files/solutions/answer.sql", headers={"User-Agent": CHROME})
        assert r.status_code == 403
        r = client.get("/files/solutions/answer.sql", headers={"User-Agent": TRUSTLOCK})
        assert r.status_code != 403
    destroy_ctfd(app)


def test_students_cannot_log_in_from_another_browser_during_the_exam():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        student_client(app).get("/logout")
        set_config("exam_browser_required", "true")

        def login(user_agent, name, password="password"):
            client = app.test_client()
            client.environ_base["HTTP_USER_AGENT"] = user_agent
            client.get("/login")
            with client.session_transaction() as sess:
                nonce = sess["nonce"]
            r = client.post(
                "/login", data={"name": name, "password": password, "nonce": nonce}
            )
            with client.session_transaction() as sess:
                return r.status_code, "id" in sess

        # a student's login from a normal browser is refused before it happens,
        # so it cannot sign the student out of the exam browser
        assert login(CHROME, "student") == (403, False)
        assert login(TRUSTLOCK, "student") == (302, True)
        # unknown names get the same answer, so student names are not revealed
        assert login(CHROME, "nobody") == (403, False)
        # admins keep logging in from anywhere, including a preset admin that
        # does not exist in the database until its first login
        assert login(CHROME, "admin") == (302, True)
        app.config["PRESET_ADMIN_NAME"] = "preset-admin"
        app.config["PRESET_ADMIN_EMAIL"] = "preset@examplectf.com"
        app.config["PRESET_ADMIN_PASSWORD"] = "preset-password"
        assert login(CHROME, "preset-admin", "preset-password") == (302, True)

        # refused attempts count against the login rate limit
        from CTFd.cache import cache

        cache.delete("rl:127.0.0.1:auth.login")
        statuses = {login(CHROME, "student")[0] for _ in range(31)}
        assert statuses == {403, 429}
        assert login(CHROME, "student")[0] == 429
    destroy_ctfd(app)
