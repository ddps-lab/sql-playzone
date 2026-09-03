#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Google-registered accounts finish onboarding before they can use the site."""

from CTFd.cache import cache
from CTFd.models import SolutionFiles, UserFieldEntries, UserFields, Users, db
from CTFd.utils import get_config, set_config
from CTFd.utils.crypto import verify_password
from CTFd.utils.security.auth import generate_user_token
from CTFd.utils.security.csrf import generate_nonce
from CTFd.utils.security.signing import hmac
from tests.helpers import (
    create_ctfd,
    destroy_ctfd,
    gen_challenge,
    gen_field,
    gen_file,
    gen_solution,
    gen_user,
    login_as_user,
)

STUDENT_ID_FIELD = "Student ID Number"  # created by the student_fields plugin
TERMS_FIELD = "Terms of Service"  # created by the onboarding plugin


def field_id(name):
    return UserFields.query.filter_by(name=name).first().id


def create_google_user(
    app, name="김민수", email="minsu@hanyang.ac.kr", password=None, student_id=None
):
    with app.app_context():
        user = Users(name=name, email=email, oauth_id=f"google_{email}", verified=True)
        if password is not None:
            user.password = password
        db.session.add(user)
        db.session.commit()
        if student_id is not None:
            # an account that already finished onboarding: student ID and consent
            db.session.add(
                UserFieldEntries(
                    field_id=field_id(STUDENT_ID_FIELD),
                    user_id=user.id,
                    value=student_id,
                )
            )
            db.session.add(
                UserFieldEntries(
                    field_id=field_id(TERMS_FIELD), user_id=user.id, value=True
                )
            )
            db.session.commit()
        return user.id


def start_session(app, user_id, via_google=True):
    """Open a session the way auth.google_callback does: no password involved."""
    client = app.test_client()
    with app.app_context():
        password_hash = db.session.query(Users.password).filter_by(id=user_id).scalar()
        nonce = generate_nonce()
        cache.set(f"user_{user_id}_active_nonce", nonce, timeout=60)
        with client.session_transaction() as sess:
            sess["id"] = user_id
            sess["nonce"] = nonce
            sess["hash"] = hmac(password_hash)
            if via_google:
                sess["google_login_nonce"] = nonce
    return client


def onboarding_data(client, **overrides):
    with client.session_transaction() as sess:
        nonce = sess["nonce"]
    data = {
        "name": "playzone-minsu",
        "password": "hunter22!",
        f"fields[{field_id(STUDENT_ID_FIELD)}]": "2025123456",
        f"fields[{field_id(TERMS_FIELD)}]": "y",
        "nonce": nonce,
    }
    data.update(overrides)
    data.setdefault("password_confirm", data["password"])
    return data


def stored_password(user_id):
    return db.session.query(Users.password).filter_by(id=user_id).scalar()


def test_google_account_without_password_is_sent_to_onboarding():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        user_id = create_google_user(app)
        client = start_session(app, user_id)

        challenge = gen_challenge(app.db)
        gen_file(app.db, location="attachments/answers.txt", challenge_id=challenge.id)
        gen_file(app.db, location="branding/logo.png")  # a site asset
        solution = gen_solution(app.db, challenge_id=challenge.id, state="visible")
        db.session.add(
            SolutionFiles(location="solutions/answer.sql", solution_id=solution.id)
        )
        db.session.commit()
        for path in (
            "/",
            "/challenges",
            "/settings",
            "/api/v1/users/me",
            "/files/attachments/answers.txt",
            "/files/solutions/answer.sql",
        ):
            r = client.get(path)
            assert r.status_code == 302, path
            assert r.location.endswith("/onboarding/"), path
        assert client.get("/files/branding/logo.png").status_code != 302

        r = client.get("/onboarding/")
        assert r.status_code == 200
        assert b"minsu@hanyang.ac.kr" in r.data
        # live password feedback uses the server's minimum length
        assert b'data-password-min-length="8"' in r.data
        assert b'data-password-max-length="128"' in r.data
        assert b'id="password-rules"' in r.data
        assert r.data.count(b'data-terms-checkbox="1"') == 1
        assert STUDENT_ID_FIELD.encode() in r.data
        # the terms are shown inline, rendered from markdown, with a consent checkbox
        assert "<h1>SQL PlayZone 이용 약관".encode() in r.data
        assert b"&lt;h1&gt;" not in r.data
        assert b"I have read and agree to the Terms of Service above." in r.data

        # logging out stays possible, and anonymous requests are untouched
        assert client.get("/logout").status_code == 302
        assert app.test_client().get("/login").status_code == 200
    destroy_ctfd(app)


def test_onboarding_sets_name_password_and_student_id_then_form_login_works():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        user_id = create_google_user(app)
        client = start_session(app, user_id)

        r = client.post("/onboarding/", data=onboarding_data(client))
        assert r.status_code == 302
        assert r.location.endswith("/challenges")

        user = Users.query.filter_by(id=user_id).first()
        assert user.name == "playzone-minsu"
        assert verify_password("hunter22!", user.password)
        field = UserFields.query.filter_by(name=STUDENT_ID_FIELD).first()
        entry = UserFieldEntries.query.filter_by(
            user_id=user_id, field_id=field.id
        ).first()
        assert entry.value == "2025123456"
        consent = UserFieldEntries.query.filter_by(
            user_id=user_id, field_id=field_id(TERMS_FIELD)
        ).first()
        assert consent.value is True

        # the session survives the password change and the gate is lifted
        assert client.get("/challenges").status_code == 200
        assert (
            client.get("/api/v1/users/me").get_json()["data"]["name"]
            == "playzone-minsu"
        )
        # this session is still Google-authenticated, so the page now offers a password change
        assert b"Set a New Password" in client.get("/onboarding/").data

        client.get("/logout")
        client = login_as_user(app, name="playzone-minsu", password="hunter22!")
        assert client.get("/api/v1/users/me").status_code == 200
        client = login_as_user(app, name="minsu@hanyang.ac.kr", password="hunter22!")
        assert client.get("/api/v1/users/me").status_code == 200
    destroy_ctfd(app)


def test_onboarding_rejects_bad_names_passwords_and_missing_student_id():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        set_config("password_min_length", 8)
        gen_user(app.db, name="taken", email="taken@examplectf.com")
        user_id = create_google_user(app)
        client = start_session(app, user_id)
        cases = [
            ({"name": "taken"}, b"That user name is already taken"),
            (
                {"name": "someone@hanyang.ac.kr"},
                b"Your user name cannot be an email address",
            ),
            ({"name": ""}, b"Pick a longer user name"),
            ({"password": "short1"}, b"Password must be at least 8 characters"),
            (
                {"password": "12345678"},
                b"Password must contain both a letter and a digit",
            ),
            (
                {"password": "password"},
                b"Password must contain both a letter and a digit",
            ),
            (
                # letters and digits are ASCII: a Roman numeral is not a digit
                {"password": "abcdefg\u2167"},
                b"Password must contain both a letter and a digit",
            ),
            (
                # and Hangul is not an English letter
                {"password": "가나다라1234"},
                b"Password must contain both a letter and a digit",
            ),
            ({"password_confirm": "hunter22?"}, b"Passwords do not match"),
            (
                {f"fields[{field_id(STUDENT_ID_FIELD)}]": ""},
                b"Please provide all required fields",
            ),
            (
                {f"fields[{field_id(TERMS_FIELD)}]": ""},
                b"Please agree to the Terms of Service to continue",
            ),
            (
                {f"fields[{field_id(TERMS_FIELD)}]": "false"},
                b"Please agree to the Terms of Service to continue",
            ),
            (
                {f"fields[{field_id(TERMS_FIELD)}]": "0"},
                b"Please agree to the Terms of Service to continue",
            ),
        ]
        for overrides, message in cases:
            # more attempts than the page's per-IP rate limit allows in 5 seconds
            cache.delete("rl:127.0.0.1:onboarding.index")
            r = client.post("/onboarding/", data=onboarding_data(client, **overrides))
            assert r.status_code == 200, overrides
            assert message in r.data, overrides
            assert stored_password(user_id) is None, overrides

        assert client.get("/challenges").status_code == 302
    destroy_ctfd(app)


def test_api_tokens_are_for_admins_only():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        create_google_user(
            app,
            name="done",
            email="done@hanyang.ac.kr",
            password="hunter22!",
            student_id="2025000003",
        )
        client = login_as_user(app, name="done", password="hunter22!")
        # a student cannot create a token ...
        r = client.post("/api/v1/tokens", json={})
        assert r.status_code == 403
        assert r.get_json()["errors"] == [
            "API tokens are available to administrators only."
        ]
        # ... and one that exists (created before this rule) does not sign in
        student = Users.query.filter_by(name="done").first()
        token = generate_user_token(student)
        headers = {
            "Authorization": f"Token {token.value}",
            "Content-Type": "application/json",
        }
        token_client = app.test_client()
        r = token_client.get("/api/v1/users/me", headers=headers)
        assert r.status_code == 403
        # ... and leaves no session cookie behind for a later request
        with token_client.session_transaction() as sess:
            assert "id" not in sess
        assert token_client.get("/api/v1/users/me").status_code != 200
        # the student's own browser session keeps working
        assert client.get("/api/v1/users/me").status_code == 200

        admin = login_as_user(app, name="admin", password="password")
        assert admin.post("/api/v1/tokens", json={}).status_code == 200
        admin_token = generate_user_token(Users.query.filter_by(name="admin").first())
        headers["Authorization"] = f"Token {admin_token.value}"
        assert (
            app.test_client().get("/api/v1/users/me", headers=headers).status_code
            == 200
        )
    destroy_ctfd(app)


def test_accounts_with_passwords_and_admins_are_not_gated():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        admin = login_as_user(app, name="admin", password="password")
        assert admin.get("/api/v1/users/me").status_code == 200
        assert admin.get("/onboarding/").location.endswith("/settings")

        create_google_user(
            app,
            name="done",
            email="done@hanyang.ac.kr",
            password="hunter22!",
            student_id="2025000003",
        )
        client = login_as_user(app, name="done", password="hunter22!")
        assert client.get("/api/v1/users/me").status_code == 200
        r = client.get("/onboarding/")
        assert r.status_code == 302
        assert r.location.endswith("/settings")
    destroy_ctfd(app)


def test_google_login_allows_a_new_password_without_the_current_one():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        user_id = create_google_user(
            app,
            name="forgot",
            email="forgot@hanyang.ac.kr",
            password="old-password",
            student_id="2025000001",
        )

        # a form login is not enough: Settings asks for the current password
        client = login_as_user(app, name="forgot", password="old-password")
        r = client.post(
            "/onboarding/",
            data=onboarding_data(client, name="forgot", password="new-pass-2026"),
        )
        assert r.status_code == 302
        assert r.location.endswith("/settings")
        assert verify_password("old-password", stored_password(user_id))

        # a session that Google authenticated must set a new password first
        client = start_session(app, user_id, via_google=True)
        for path in ("/challenges", "/challenges", "/settings", "/api/v1/users/me"):
            r = client.get(path)
            assert r.status_code == 302, path
            assert r.location.endswith("/onboarding/"), path
        r = client.get("/onboarding/")
        assert r.status_code == 200
        assert b"Set a New Password" in r.data
        assert b"Skip for now" not in r.data
        assert STUDENT_ID_FIELD.encode() not in r.data

        # a password reset leaves custom fields alone, even ones the settings
        # page would refuse to change
        cohort = gen_field(app.db, name="Cohort", editable=False, required=True)
        db.session.add(UserFieldEntries(field_id=cohort.id, user_id=user_id, value="A"))
        db.session.commit()
        with client.session_transaction() as sess:
            nonce = sess["nonce"]
        r = client.post(
            "/onboarding/",
            data={
                "name": "forgot",
                "password": "new-pass-2026",
                "password_confirm": "new-pass-2026",
                f"fields[{cohort.id}]": "B",
                "nonce": nonce,
            },
        )
        assert r.status_code == 302
        assert r.location.endswith("/challenges")
        assert verify_password("new-pass-2026", stored_password(user_id))
        assert client.get("/challenges").status_code == 200
        assert client.get("/api/v1/users/me").status_code == 200
        entry = UserFieldEntries.query.filter_by(
            user_id=user_id, field_id=cohort.id
        ).first()
        assert entry.value == "A"

        # the marker is tied to the nonce Google logged in with
        client = start_session(app, user_id, via_google=False)
        assert client.get("/onboarding/").status_code == 302
    destroy_ctfd(app)


def test_google_login_requires_a_new_password_in_teams_mode_too():
    app = create_ctfd(enable_plugins=True, user_mode="teams")
    with app.app_context():
        user_id = create_google_user(
            app,
            name="teamless",
            email="teamless@hanyang.ac.kr",
            password="old-password",
            student_id="2025000002",
        )
        client = start_session(app, user_id, via_google=True)
        # the callback lands teamless users on the team page, not the challenges
        r = client.get("/team")
        assert r.status_code == 302
        assert r.location.endswith("/onboarding/")
        assert client.get("/team").status_code == 302
        r = client.post(
            "/onboarding/",
            data=onboarding_data(client, name="teamless", password="new-pass-2026"),
        )
        assert r.status_code == 302
        assert client.get("/team").status_code == 200
    destroy_ctfd(app)


def test_terms_are_seeded_and_linked_from_the_footer():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        client = app.test_client()
        r = client.get("/tos")
        assert r.status_code == 200
        assert "실행(Test/Execute)한 SQL".encode() in r.data
        field = UserFields.query.filter_by(name=TERMS_FIELD).first()
        assert (field.required, field.editable, field.public) == (True, False, False)
        # the settings page enforces the same minimum length
        assert int(get_config("password_min_length")) == 8

        app.config["GOOGLE_CLIENT_ID"] = "client"  # render the Google section
        html = client.get("/login").data
        assert b'href="/tos"' in html
        assert b"<span data-copyright-year>2026</span>" in html
        # no email reset: Google is the sign-up and the reset path
        assert b"/reset_password" not in html
        assert b"Sign up or reset password with HYU Google" in html
    destroy_ctfd(app)


def test_existing_accounts_are_asked_for_consent_once():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        # an account from before the consent field existed: password and
        # student ID, but no terms entry
        user_id = gen_user(app.db, name="veteran", email="veteran@examplectf.com").id
        db.session.add(
            UserFieldEntries(
                field_id=field_id(STUDENT_ID_FIELD), user_id=user_id, value="2024000001"
            )
        )
        # an imported "no" is not consent either
        db.session.add(
            UserFieldEntries(
                field_id=field_id(TERMS_FIELD), user_id=user_id, value=False
            )
        )
        db.session.commit()
        client = login_as_user(app, name="veteran", password="password")

        # nothing but logout works until the terms are accepted
        for path in ("/challenges", "/settings", "/api/v1/users/me"):
            r = client.get(path)
            assert r.status_code == 302, path
            assert r.location.endswith("/onboarding/"), path

        r = client.get("/onboarding/")
        assert r.status_code == 200
        assert b"Please read and agree to the Terms of Service" in r.data
        assert b'name="password"' not in r.data
        assert b'id="password-rules"' not in r.data
        assert STUDENT_ID_FIELD.encode() not in r.data

        with client.session_transaction() as sess:
            nonce = sess["nonce"]
        r = client.post("/onboarding/", data={"nonce": nonce})
        assert r.status_code == 200
        assert b"Please agree to the Terms of Service to continue" in r.data

        r = client.post(
            "/onboarding/",
            data={f"fields[{field_id(TERMS_FIELD)}]": "y", "nonce": nonce},
        )
        assert r.status_code == 302
        assert r.location.endswith("/challenges")
        consent = UserFieldEntries.query.filter_by(
            user_id=user_id, field_id=field_id(TERMS_FIELD)
        ).first()
        assert consent.value is True
        assert verify_password("password", stored_password(user_id))
        assert client.get("/challenges").status_code == 200
        assert client.get("/api/v1/users/me").status_code == 200
        assert client.get("/onboarding/").location.endswith("/settings")
    destroy_ctfd(app)


def test_other_oauth_accounts_only_get_the_terms():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        # an account from CTFd's own OAuth integration: no password, no google_ prefix
        user = Users(name="mlc", email="mlc@examplectf.com", oauth_id="1337")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        client = start_session(app, user_id, via_google=False)

        r = client.get("/challenges")
        assert r.status_code == 302
        assert r.location.endswith("/onboarding/")
        r = client.get("/onboarding/")
        assert r.status_code == 200
        assert b'name="password"' not in r.data
        assert STUDENT_ID_FIELD.encode() not in r.data

        with client.session_transaction() as sess:
            nonce = sess["nonce"]
        r = client.post(
            "/onboarding/",
            data={f"fields[{field_id(TERMS_FIELD)}]": "y", "nonce": nonce},
        )
        assert r.status_code == 302
        assert stored_password(user_id) is None
        assert client.get("/api/v1/users/me").status_code == 200
        assert client.get("/onboarding/").location.endswith("/settings")
    destroy_ctfd(app)


def test_consent_field_and_terms_come_back_after_an_import():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        # a CTFd import replaces the tables while the app keeps running
        UserFields.query.filter_by(name=TERMS_FIELD).delete()
        db.session.commit()
        set_config("tos_text", "")
        set_config("password_min_length", 4)

        # any request restores the password floor, before onboarding is visited
        assert app.test_client().get("/login").status_code == 200
        assert int(get_config("password_min_length")) == 8

        user_id = create_google_user(app)
        client = start_session(app, user_id)
        r = client.get("/onboarding/")
        assert r.status_code == 200
        assert "<h1>SQL PlayZone 이용 약관".encode() in r.data
        assert UserFields.query.filter_by(name=TERMS_FIELD).count() == 1
        assert "8–128 characters".encode() in r.data

        # the gate is back for accounts that never accepted the terms
        gen_user(app.db, name="veteran", email="veteran@examplectf.com")
        client = login_as_user(app, name="veteran", password="password")
        r = client.get("/challenges")
        assert r.status_code == 302
        assert r.location.endswith("/onboarding/")
    destroy_ctfd(app)


def test_duplicate_consent_fields_are_folded_into_the_first():
    from CTFd.plugins.onboarding import terms_field

    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        first_id = field_id(TERMS_FIELD)
        # a second worker created the field at the same time
        duplicate_id = gen_field(
            app.db, name=TERMS_FIELD, field_type="boolean", editable=False, public=False
        ).id
        user_id = create_google_user(app, password="hunter22!", student_id="2025000005")
        UserFieldEntries.query.filter_by(user_id=user_id, field_id=first_id).delete()
        db.session.add(
            UserFieldEntries(field_id=duplicate_id, user_id=user_id, value=True)
        )
        db.session.commit()

        # another user answered under both fields: no under the kept one,
        # yes under the duplicate
        other_id = create_google_user(
            app, name="둘다", email="both@hanyang.ac.kr", password="hunter22!"
        )
        db.session.add(
            UserFieldEntries(field_id=first_id, user_id=other_id, value=False)
        )
        db.session.add(
            UserFieldEntries(field_id=duplicate_id, user_id=other_id, value=True)
        )
        db.session.commit()

        assert terms_field().id == first_id
        assert UserFields.query.filter_by(name=TERMS_FIELD).count() == 1
        # the entry recorded against the duplicate now counts for the kept field
        client = login_as_user(app, name="김민수", password="hunter22!")
        assert client.get("/api/v1/users/me").status_code == 200
        entries = UserFieldEntries.query.filter_by(user_id=other_id).all()
        assert [(e.field_id, e.value) for e in entries] == [(first_id, True)]
        client = login_as_user(app, name="둘다", password="hunter22!")
        assert client.get("/api/v1/users/me").status_code == 200
    destroy_ctfd(app)


def test_a_preset_password_minimum_below_the_floor_is_not_rewritten():
    from CTFd.models import Configs
    from CTFd.plugins.onboarding import password_min_length

    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        app.config["PRESET_CONFIGS"] = {"password_min_length": 4}
        stored_before = Configs.query.filter_by(key="password_min_length").first().value
        assert password_min_length() == 8
        assert password_min_length() == 8
        assert (
            Configs.query.filter_by(key="password_min_length").first().value
            == stored_before
        )
        # the onboarding page still enforces the floor on its own
        user_id = create_google_user(app)
        client = start_session(app, user_id)
        r = client.post(
            "/onboarding/",
            data=onboarding_data(
                client, password="ab12345", password_confirm="ab12345"
            ),
        )
        assert r.status_code == 200
        assert b"Password must be at least 8 characters" in r.data
        app.config["PRESET_CONFIGS"] = None
    destroy_ctfd(app)


def test_an_older_text_field_with_the_same_name_is_normalized():
    from CTFd.plugins.onboarding import terms_field

    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        field = UserFields.query.filter_by(name=TERMS_FIELD).first()
        field.field_type = "text"
        field.required = False
        field.editable = True
        field.public = True
        db.session.commit()

        field = terms_field()
        assert (field.field_type, field.required, field.editable, field.public) == (
            "boolean",
            True,
            False,
            False,
        )
        # a "y" recorded while it was a text field still counts as consent
        user_id = create_google_user(app, password="hunter22!", student_id="2025000006")
        UserFieldEntries.query.filter_by(user_id=user_id, field_id=field.id).update(
            {"value": "y"}
        )
        db.session.commit()
        client = login_as_user(app, name="김민수", password="hunter22!")
        assert client.get("/api/v1/users/me").status_code == 200
    destroy_ctfd(app)


def test_google_session_without_consent_does_consent_then_password_reset():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        # an account from before the consent field: password, no consent
        user_id = create_google_user(
            app, name="upgraded", email="up@hanyang.ac.kr", password="old-pass-1"
        )
        client = start_session(app, user_id, via_google=True)
        r = client.get("/onboarding/")
        assert b"Please read and agree to the Terms of Service" in r.data
        with client.session_transaction() as sess:
            nonce = sess["nonce"]
        r = client.post(
            "/onboarding/",
            data={f"fields[{field_id(TERMS_FIELD)}]": "y", "nonce": nonce},
        )
        assert r.status_code == 302

        # consent alone does not end the Google session's onboarding
        r = client.get("/challenges")
        assert r.status_code == 302
        assert r.location.endswith("/onboarding/")
        assert b"Set a New Password" in client.get("/onboarding/").data
        assert verify_password("old-pass-1", stored_password(user_id))

        r = client.post(
            "/onboarding/",
            data=onboarding_data(client, name="upgraded", password="new-pass-2026"),
        )
        assert r.status_code == 302
        assert verify_password("new-pass-2026", stored_password(user_id))
        assert (
            client.get("/challenges").status_code == 302
        )  # no student ID yet: CTFd sends to settings
        assert client.get("/challenges").location.endswith("/settings")
    destroy_ctfd(app)


def test_students_cannot_change_their_email_but_admins_can():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        create_google_user(
            app,
            name="fixed",
            email="fixed@hanyang.ac.kr",
            password="hunter22!",
            student_id="2025000007",
        )
        client = login_as_user(app, name="fixed", password="hunter22!")
        r = client.patch("/api/v1/users/me", json={"email": "other@hanyang.ac.kr"})
        assert r.status_code == 400
        assert "email" in r.get_json()["errors"]
        r = client.patch(
            "/api/v1/users/me", json={"email": "fixed@hanyang.ac.kr", "name": "fixed2"}
        )
        assert r.status_code == 200
        assert (
            Users.query.filter_by(name="fixed2").first().email == "fixed@hanyang.ac.kr"
        )
        assert b"cannot be changed here" in client.get("/settings").data

        admin = login_as_user(app, name="admin", password="password")
        r = admin.patch("/api/v1/users/me", json={"email": "admin2@examplectf.com"})
        assert r.status_code == 200
    destroy_ctfd(app)
