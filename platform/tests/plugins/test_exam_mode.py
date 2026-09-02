#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Exam browser restriction: students must use the lockdown browser when enabled."""

from CTFd.models import UserFieldEntries, UserFields, Users, db
from CTFd.utils import get_config, set_config
from tests.helpers import create_ctfd, destroy_ctfd, gen_user, login_as_user

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
