#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A newer login signs the older session out on its very next request."""

from CTFd.models import UserFieldEntries, UserFields, db
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
