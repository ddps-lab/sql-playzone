#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Accounts log in with a unique ID or their email; the nickname is a display name."""

from CTFd.models import Users
from tests.helpers import create_ctfd, destroy_ctfd, gen_user, login_as_user


def test_login_uses_the_id_or_the_email_but_not_the_nickname():
    app = create_ctfd()
    with app.app_context():
        gen_user(app.db, name="홍길동", email="hong@hanyang.ac.kr", login_id="hong1")
        for handle in ("hong1", "hong@hanyang.ac.kr"):
            client = login_as_user(app, name=handle, password="password")
            assert client.get("/api/v1/users/me").status_code == 200
        client = login_as_user(
            app, name="홍길동", password="password", raise_for_error=False
        )
        assert client.get("/api/v1/users/me").status_code != 200
    destroy_ctfd(app)


def test_nicknames_may_repeat_but_login_ids_may_not():
    app = create_ctfd()
    with app.app_context():
        admin = login_as_user(app, name="admin", password="password")
        for login_id, email in (
            ("hong1", "a@hanyang.ac.kr"),
            ("hong2", "b@hanyang.ac.kr"),
        ):
            r = admin.post(
                "/api/v1/users",
                json={
                    "name": "홍길동",
                    "login_id": login_id,
                    "email": email,
                    "password": "password",
                },
            )
            assert r.status_code == 200, r.get_json()
        assert Users.query.filter_by(name="홍길동").count() == 2

        r = admin.post(
            "/api/v1/users",
            json={
                "name": "홍길동",
                "login_id": "HONG1",
                "email": "c@hanyang.ac.kr",
                "password": "password",
            },
        )
        assert r.status_code == 400
        assert "already taken" in r.get_json()["errors"]["login_id"][0]

        r = admin.post(
            "/api/v1/users",
            json={
                "name": "x",
                "login_id": "not ok",
                "email": "d@hanyang.ac.kr",
                "password": "password",
            },
        )
        assert r.status_code == 400
        assert "3 to 32" in r.get_json()["errors"]["login_id"][0]
    destroy_ctfd(app)


def test_admin_creation_reuses_the_name_as_the_id_when_it_is_usable():
    app = create_ctfd()
    with app.app_context():
        admin = login_as_user(app, name="admin", password="password")
        r = admin.post(
            "/api/v1/users",
            json={
                "name": "student7",
                "email": "s7@hanyang.ac.kr",
                "password": "password",
            },
        )
        assert r.status_code == 200
        assert (
            Users.query.filter_by(email="s7@hanyang.ac.kr").first().login_id
            == "student7"
        )

        r = admin.post(
            "/api/v1/users",
            json={"name": "홍길동", "email": "h@hanyang.ac.kr", "password": "password"},
        )
        assert r.status_code == 200
        assert Users.query.filter_by(email="h@hanyang.ac.kr").first().login_id is None
        # such an account logs in with its email address
        client = login_as_user(app, name="h@hanyang.ac.kr", password="password")
        assert client.get("/api/v1/users/me").status_code == 200

        # an admin edit can set the ID later, and it must stay unique
        user_id = Users.query.filter_by(email="h@hanyang.ac.kr").first().id
        assert (
            admin.patch(
                f"/api/v1/users/{user_id}", json={"login_id": "hong"}
            ).status_code
            == 200
        )
        assert (
            admin.patch(
                f"/api/v1/users/{user_id}", json={"login_id": "student7"}
            ).status_code
            == 400
        )
        assert Users.query.filter_by(id=user_id).first().login_id == "hong"
    destroy_ctfd(app)


def test_students_cannot_change_their_id_and_do_not_see_others():
    app = create_ctfd()
    with app.app_context():
        gen_user(app.db, name="홍길동", email="hong@hanyang.ac.kr", login_id="hong1")
        other_id = gen_user(
            app.db, name="김철수", email="kim@hanyang.ac.kr", login_id="kim1"
        ).id
        client = login_as_user(app, name="hong1", password="password")
        r = client.patch("/api/v1/users/me", json={"login_id": "hong9"})
        assert r.status_code == 400
        assert (
            Users.query.filter_by(email="hong@hanyang.ac.kr").first().login_id
            == "hong1"
        )
        # the nickname may still be edited, even to a name someone else uses
        r = client.patch("/api/v1/users/me", json={"name": "김철수"})
        assert r.status_code == 200, r.get_json()
        assert (
            "login_id" not in client.get(f"/api/v1/users/{other_id}").get_json()["data"]
        )
        page = client.get("/settings").data.decode()
        assert 'value="hong1" disabled' in page
        assert "Nickname" in page
    destroy_ctfd(app)


def test_the_login_form_asks_for_the_id_or_email():
    app = create_ctfd()
    with app.app_context():
        assert b"ID or Email" in app.test_client().get("/login").data
    destroy_ctfd(app)
