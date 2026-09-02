#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Google sign-in only admits verified accounts from the course domain."""

from unittest.mock import Mock, patch

import requests

from CTFd.models import Users, db
from tests.helpers import create_ctfd, destroy_ctfd


def google_userinfo(email, verified=True, hd="hanyang.ac.kr"):
    info = {"id": "1", "email": email, "verified_email": verified, "name": "Student"}
    if hd is not None:
        info["hd"] = hd
    return info


def google_callback(client, userinfo):
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
        return client.get("/google/callback?code=code&state=state")


def create_google_ctfd():
    app = create_ctfd()
    app.config["GOOGLE_CLIENT_ID"] = "client"
    app.config["GOOGLE_CLIENT_SECRET"] = "secret"
    return app


def test_google_callback_rejects_accounts_outside_the_course_domain():
    app = create_google_ctfd()
    with app.app_context():
        rejected = (
            google_userinfo("someone@gmail.com"),
            google_userinfo("someone@hanyang.ac.kr", verified=False),
            google_userinfo("someone@hanyang.ac.kr.example.com"),
            google_userinfo("someone@sub.hanyang.ac.kr"),
            # a consumer account registered with a university address
            google_userinfo("someone@hanyang.ac.kr", hd=None),
            google_userinfo("someone@hanyang.ac.kr", hd="other.ac.kr"),
        )
        for userinfo in rejected:
            client = app.test_client()
            r = google_callback(client, userinfo)
            assert r.status_code == 302, userinfo
            assert r.location.endswith("/login"), userinfo
            with client.session_transaction() as sess:
                assert "id" not in sess, userinfo
        assert Users.query.filter(Users.type != "admin").count() == 0
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
