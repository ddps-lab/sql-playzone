#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The Access Tokens tab of the settings page is for admins only."""

from tests.helpers import create_ctfd, destroy_ctfd, login_as_user, register_user


def test_students_do_not_see_the_access_tokens_tab():
    app = create_ctfd()
    with app.app_context():
        register_user(app)
        client = login_as_user(app)
        r = client.get("/settings")
        assert r.status_code == 200
        assert "Access Tokens" not in r.get_data(as_text=True)
        assert 'id="tokens"' not in r.get_data(as_text=True)

        admin = login_as_user(app, name="admin", password="password")
        r = admin.get("/settings")
        assert r.status_code == 200
        assert "Access Tokens" in r.get_data(as_text=True)
    destroy_ctfd(app)
