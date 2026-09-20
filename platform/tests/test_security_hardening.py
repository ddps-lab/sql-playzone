"""Regressions for student-visible data, transport, and request admission."""

from io import BytesIO

from freezegun import freeze_time

from CTFd.models import Users
from CTFd.utils.scores import get_standings
from tests.helpers import (
    create_ctfd, destroy_ctfd, gen_user, gen_challenge, gen_solve, login_as_user,
)


def test_hidden_results_do_not_leak_through_profiles_or_scoreboard():
    app = create_ctfd()
    try:
        with app.app_context():
            student = gen_user(app.db, name="student", email="student@examplectf.com")
            visible = gen_challenge(app.db, name="visible", value=10, state="visible")
            hidden = gen_challenge(app.db, name="secret", value=100, state="hidden")
            locked = gen_challenge(app.db, name="locked", value=50, state="locked")
            for challenge in (visible, hidden, locked):
                gen_solve(app.db, user_id=student.id, challenge_id=challenge.id)
                gen_solve(app.db, user_id=1, challenge_id=challenge.id)
            uid, visible_id = student.id, visible.id
            client = login_as_user(app, name="student")
            student = Users.query.get(uid)
            assert student.get_score() == 10
            assert student.get_score(admin=True) == 160
            assert [s.challenge_id for s in student.get_solves()] == [visible_id]
            standings = get_standings()
            assert [(s.account_id, s.score) for s in standings] == [(uid, 10)]
            detail = client.get("/api/v1/scoreboard/top/10").get_json()["data"]
            assert [s["challenge_id"] for s in detail["1"]["solves"]] == [visible_id]
            public = client.get(f"/api/v1/users/{uid}/solves").get_json()["data"]
            assert [s["challenge_id"] for s in public] == [visible_id]
    finally:
        destroy_ctfd(app)


def test_cookie_flags_hsts_and_oversized_anonymous_form():
    app = create_ctfd()
    try:
        app.config.update(SESSION_COOKIE_SECURE=True, MAX_CONTENT_LENGTH=1024)
        client = app.test_client()
        response = client.get("/login", base_url="https://localhost")
        cookie = response.headers["Set-Cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
        assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
        assert "Strict-Transport-Security" not in client.get("/login").headers
        response = client.post("/login", data={"name": "x" * 2048})
        assert response.status_code == 413
        response = client.post("/login", data={"file": (BytesIO(b"x" * 2048), "test.bin")})
        assert response.status_code == 413
    finally:
        destroy_ctfd(app)


def login_client(app, address):
    client = app.test_client()
    client.environ_base["REMOTE_ADDR"] = address

    def attempt(name, password):
        # Logging out rotates the session, so read the CSRF nonce each time.
        client.get("/login")
        with client.session_transaction() as session:
            nonce = session["nonce"]
        return client.post(
            "/login", data={"name": name, "password": password, "nonce": nonce}
        )

    attempt.logout = lambda: client.get("/logout")
    return attempt


def test_login_failures_are_budgeted_per_account_and_address():
    app = create_ctfd()
    try:
        with app.app_context(), freeze_time("2026-09-20T12:00:01Z"):
            gen_user(app.db, name="student", email="student@examplectf.com")
            classroom = login_client(app, "192.0.2.1")
            home = login_client(app, "192.0.2.2")
            for i in range(10):
                name = "student" if i % 2 else "STUDENT@examplectf.com"
                assert classroom(name, "wrong").status_code == 200
            # The eleventh attempt from the same address is refused even with
            # the right password, but another address is unaffected.
            assert classroom("student", "password").status_code == 429
            assert home("student", "password").status_code == 302
            home.logout()
            # Successful logins never count and clear earlier failures.
            for _ in range(9):
                assert home("student", "wrong").status_code == 200
            assert home("student", "password").status_code == 302
            home.logout()
            for _ in range(10):
                assert home("student", "wrong").status_code == 200
            assert home("student", "password").status_code == 429
        with freeze_time("2026-09-20T12:15:02Z"):
            assert classroom("student", "password").status_code == 302
    finally:
        destroy_ctfd(app)
