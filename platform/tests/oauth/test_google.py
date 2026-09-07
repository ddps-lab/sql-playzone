#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Google sign-in only admits verified Google Workspace (school) accounts."""

from unittest.mock import Mock, patch

import requests

from CTFd.models import Users, db
from tests.helpers import create_ctfd, destroy_ctfd


def google_userinfo(email, verified=True, hd="hanyang.ac.kr", uid="1"):
    info = {"id": uid, "email": email, "verified_email": verified, "name": "Student"}
    if hd is not None:
        info["hd"] = hd
    return info


def google_callback(client, userinfo, follow_redirects=False):
    """Complete /google/callback with Google's token and userinfo calls faked."""
    with patch.object(requests, "post") as fake_post, patch.object(
        requests, "get"
    ) as fake_get:
        fake_post.return_value = Mock(
            status_code=200, json=lambda: {"access_token": "token"}
        )
        fake_get.return_value = Mock(status_code=200, json=lambda: userinfo)
        with client.session_transaction() as sess:
            sess["google_oauth_state"] = "state"
        return client.get(
            "/google/callback?code=code&state=state", follow_redirects=follow_redirects
        )


def create_google_ctfd():
    app = create_ctfd()
    app.config["GOOGLE_CLIENT_ID"] = "client"
    app.config["GOOGLE_CLIENT_SECRET"] = "secret"
    return app


def assert_rejected(app, userinfo):
    client = app.test_client()
    r = google_callback(client, userinfo)
    assert r.status_code == 302, userinfo
    assert r.location.endswith("/login"), userinfo
    with client.session_transaction() as sess:
        assert "id" not in sess, userinfo


def assert_admitted(app, userinfo):
    client = app.test_client()
    r = google_callback(client, userinfo)
    assert r.status_code == 302, userinfo
    assert r.location.endswith("/challenges"), userinfo
    with client.session_transaction() as sess:
        assert sess["id"], userinfo


def test_google_callback_rejects_consumer_and_unverified_accounts():
    app = create_google_ctfd()
    with app.app_context():
        rejected = (
            # consumer accounts never carry a Workspace domain (hd)
            google_userinfo("someone@gmail.com", hd=None),
            google_userinfo("someone@googlemail.com", hd=None),
            google_userinfo("someone@naver.com", hd=None),
            # a consumer account registered with a university address
            google_userinfo("someone@hanyang.ac.kr", hd=None),
            google_userinfo("someone@other.ac.kr", hd=None),
            google_userinfo("someone@gmail.com", hd=""),
            # unverified, or an address that does not belong to the claimed domain
            google_userinfo("someone@hanyang.ac.kr", verified=False),
            google_userinfo("someone@hanyang.ac.kr.example.com"),
            google_userinfo("someone@sub.hanyang.ac.kr"),
            google_userinfo("someone@hanyang.ac.kr", hd="other.ac.kr"),
        )
        for userinfo in rejected:
            assert_rejected(app, userinfo)
        assert Users.query.filter(Users.type != "admin").count() == 0
    destroy_ctfd(app)


def test_google_callback_admits_workspace_accounts_from_any_school_by_default():
    app = create_google_ctfd()
    with app.app_context():
        admitted = (
            google_userinfo("Student@hanyang.ac.kr", uid="1"),
            google_userinfo("exchange@other.ac.kr", hd="other.ac.kr", uid="2"),
            # Google may report the domain in another case
            google_userinfo("visitor@univ.edu", hd="UNIV.EDU", uid="3"),
        )
        for userinfo in admitted:
            assert_admitted(app, userinfo)
        assert Users.query.filter(Users.type != "admin").count() == 3
    destroy_ctfd(app)


def test_the_allowed_domains_come_from_the_configuration():
    app = create_google_ctfd()
    with app.app_context():
        app.config["GOOGLE_HOSTED_DOMAIN"] = "hanyang.ac.kr"
        assert_rejected(app, google_userinfo("someone@other.ac.kr", hd="other.ac.kr"))
        assert_rejected(app, google_userinfo("someone@gmail.com", hd=None))
        assert_admitted(app, google_userinfo("someone@hanyang.ac.kr", uid="1"))

        app.config["GOOGLE_HOSTED_DOMAIN"] = " Hanyang.ac.kr , partner.edu "
        assert_admitted(
            app, google_userinfo("someone@partner.edu", hd="partner.edu", uid="2")
        )
        assert_admitted(app, google_userinfo("other@hanyang.ac.kr", uid="3"))
        assert_rejected(
            app, google_userinfo("someone@third.edu", hd="third.edu", uid="4")
        )

        # an empty setting means any Workspace domain
        app.config["GOOGLE_HOSTED_DOMAIN"] = ""
        assert_admitted(
            app, google_userinfo("someone@third.edu", hd="third.edu", uid="4")
        )
        assert_rejected(app, google_userinfo("someone@gmail.com", hd=None))
    destroy_ctfd(app)


def test_the_rejection_explains_the_account_rule():
    app = create_google_ctfd()
    with app.app_context():
        r = google_callback(
            app.test_client(),
            google_userinfo("someone@gmail.com", hd=None),
            follow_redirects=True,
        )
        assert (
            b"Only verified university Google accounts (Google Workspace) can sign in"
            in r.data
        )
        assert b"Gmail" in r.data

        app.config["GOOGLE_HOSTED_DOMAIN"] = "hanyang.ac.kr"
        r = google_callback(
            app.test_client(),
            google_userinfo("someone@other.ac.kr", hd="other.ac.kr"),
            follow_redirects=True,
        )
        assert b"Only verified hanyang.ac.kr Google accounts can sign in" in r.data
    destroy_ctfd(app)


def test_google_login_hints_google_about_the_allowed_accounts():
    app = create_google_ctfd()
    with app.app_context():
        r = app.test_client().get("/google/login")
        assert r.status_code == 302
        assert r.location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        # any Workspace account: Google's picker hint for organization accounts
        assert "&hd=*" in r.location

        app.config["GOOGLE_HOSTED_DOMAIN"] = "hanyang.ac.kr"
        r = app.test_client().get("/google/login")
        assert "&hd=hanyang.ac.kr" in r.location

        app.config["GOOGLE_HOSTED_DOMAIN"] = "hanyang.ac.kr,partner.edu"
        r = app.test_client().get("/google/login")
        assert "&hd=*" in r.location
    destroy_ctfd(app)


def test_google_callback_admits_verified_course_accounts():
    app = create_google_ctfd()
    with app.app_context():
        client = app.test_client()
        r = google_callback(client, google_userinfo("Student@hanyang.ac.kr"))
        assert r.status_code == 302
        assert r.location.endswith("/challenges")
        with client.session_transaction() as sess:
            assert sess["id"]
            # marks the session for the onboarding plugin's password reset mode
            assert sess["google_login_nonce"] == sess["nonce"]
        user = Users.query.filter_by(email="Student@hanyang.ac.kr").first()
        assert user.oauth_id == "google_1"
        assert user.password is None
    destroy_ctfd(app)


def test_google_callback_finds_the_account_by_google_id_after_an_email_edit():
    app = create_google_ctfd()
    with app.app_context():
        user = Users(name="edited", email="edited@hanyang.ac.kr", oauth_id="google_1")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        client = app.test_client()
        r = google_callback(client, google_userinfo("Student@hanyang.ac.kr"))
        assert r.status_code == 302
        with client.session_transaction() as sess:
            assert sess["id"] == user_id
        assert Users.query.filter(Users.type != "admin").count() == 1
    destroy_ctfd(app)
