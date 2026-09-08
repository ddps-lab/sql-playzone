#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytest

from CTFd.models import Users, db
from CTFd.utils import get_config, set_config
from tests.helpers import create_ctfd, destroy_ctfd, gen_user, login_as_user


@pytest.fixture
def legal_app():
    app = create_ctfd(enable_plugins=True)
    yield app
    destroy_ctfd(app)


def test_seeded_notices_are_public_and_linked_from_home(legal_app):
    with legal_app.app_context():
        client = legal_app.test_client()
        for path, heading in (("/tos", "서비스 이용약관"), ("/privacy", "개인정보처리방침")):
            response = client.get(path)
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert f"<h1>SQL PlayZone {heading}</h1>" in html
            assert '<article class="col-12 col-lg-9 legal-content" lang="ko">' in html
            assert client.head(path).status_code == 200
        home = client.get("/")
        assert home.status_code == 200
        html = home.get_data(as_text=True)
        assert 'href="/tos"' in html
        assert 'href="/privacy"' in html
        assert "portal.hanyang.ac.kr/PiopAct" not in html


@pytest.mark.parametrize("key", ["tos", "privacy"])
@pytest.mark.parametrize("external", [False, True])
def test_startup_preserves_admin_legal_settings(legal_app, key, external):
    from CTFd.plugins.legal import load

    with legal_app.app_context():
        url = f"https://example.org/{key}" if external else ""
        text = "" if external else "# Administrator policy"
        set_config(f"{key}_url", url)
        set_config(f"{key}_text", text)
        load(legal_app)
        assert (get_config(f"{key}_url") or "") == url
        assert (get_config(f"{key}_text") or "") == text
        client = legal_app.test_client()
        response = client.get(f"/{key}")
        if external:
            assert response.status_code == 302
            assert response.location == url
            assert f'href="{url}"' in client.get("/").get_data(as_text=True)
        else:
            assert response.status_code == 200
            assert "<h1>Administrator policy</h1>" in response.get_data(as_text=True)


@pytest.mark.parametrize("restriction", ["banned", "change_password"])
def test_restricted_accounts_can_read_public_notices(legal_app, restriction):
    with legal_app.app_context():
        gen_user(db, name="reader")
        client = login_as_user(legal_app, name="reader")
        user = Users.query.filter_by(name="reader").one()
        setattr(user, restriction, True)
        db.session.commit()
        from CTFd.cache import clear_user_session

        clear_user_session(user_id=user.id)
        for path in ("/", "/tos", "/privacy"):
            assert client.get(path).status_code == 200
        assert client.get("/settings").status_code in (302, 403)


@pytest.mark.parametrize("signed_in", [False, True])
def test_exam_and_onboarding_gates_keep_notices_public(legal_app, signed_in):
    from tests.helpers import gen_page
    from tests.plugins.test_onboarding import create_google_user, start_session

    with legal_app.app_context():
        gen_page(db, title="Course only", route="course-only", content="Course material")
        if signed_in:
            user_id = create_google_user(legal_app)
            client = start_session(legal_app, user_id)
            # Consent has not been given yet; the policy link must still open.
            assert client.get("/settings").location.endswith("/onboarding/")
            assert 'href="/privacy"' in client.get("/onboarding/").get_data(as_text=True)
        else:
            client = legal_app.test_client()
        set_config("exam_mode_enabled", "true")
        set_config("exam_mode_allowed_ids", "9999999999")
        set_config("exam_browser_required", "true")
        for path in ("/", "/tos", "/privacy"):
            assert client.get(path).status_code == 200
        for path in ("/challenges", "/course-only", "/api/v1/challenges"):
            assert client.get(path).status_code in (302, 403)


def test_legal_settings():
    app = create_ctfd()
    with app.app_context():
        set_config("tos_text", "Terms of Service")
        set_config("privacy_text", "Privacy Policy")

        with app.test_client() as client:
            r = client.get("/register")
            assert r.status_code == 200
            assert "privacy policy" in r.get_data(as_text=True)
            assert "terms of service" in r.get_data(as_text=True)

            r = client.get("/tos")
            assert r.status_code == 200
            assert "Terms of Service" in r.get_data(as_text=True)

            r = client.get("/privacy")
            assert r.status_code == 200
            assert "Privacy Policy" in r.get_data(as_text=True)
    destroy_ctfd(app)
