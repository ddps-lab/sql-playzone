"""One active session per account, checked on every request, with a login trail.

Logging in stores the session's nonce as the account's active nonce in
the cache, and the fork's ``get_current_user()`` signs out any other
session it sees. That check only runs on pages that load the full user,
so an older session could still open the scoreboard or a challenge page
after a newer login. The request hook here runs the same check for
every request.

Because only one session is ever alive, the sequence of logins is the
complete record of who held an account and when. Each login is logged
with the browser and the previous login of the same account, so an exam
review only needs the logins stream.
"""

import time

from flask import abort, g, redirect, request, session, url_for

from CTFd.cache import cache
from CTFd.utils.helpers import error_for
from CTFd.utils.logging import log
from CTFd.utils.security.auth import logout_user
from CTFd.utils.user import authed, get_current_user_attrs

# Requests that need no session check: leaving, static files, health probes.
EXEMPT_ENDPOINTS = {
    "auth.logout",
    "views.themes",
    "views.themes_beta",
    "views.healthcheck",
    "static",
}
LOGIN_ENDPOINTS = {
    "auth.login": "form",
    "auth.google_callback": "google",
    "auth.oauth_redirect": "mlc",
}
LAST_LOGIN_TTL = 30 * 24 * 3600
SIGNED_OUT_MESSAGE = (
    "This account signed in from another browser, so this session was signed out. "
    "다른 브라우저에서 로그인되어 이 세션은 로그아웃되었습니다."
)


def authenticated_by_token():
    """Mirror of the condition under which CTFd's tokens hook logs in.

    Only such requests carry a per-request login with a fresh nonce; a
    bare Authorization header on any other request proves nothing.
    """
    if not request.headers.get("Authorization"):
        return False
    return request.is_json or (
        request.endpoint == "api.files_files_list"
        and request.method == "POST"
        and request.mimetype == "multipart/form-data"
    )


def is_api_request():
    # The API blueprint, not the URL prefix: APPLICATION_ROOT may be set.
    return request.is_json or str(request.endpoint or "").startswith("api.")


def session_is_current():
    active_nonce = cache.get(f"user_{session['id']}_active_nonce")
    return not active_nonce or session.get("nonce") == active_nonce


def browser():
    return (request.user_agent.string or "")[:120]


def last_login_key(user_id):
    return f"user_{user_id}_last_login"


def record_login(via):
    """One line per login: browser and the previous login of the account."""
    user = get_current_user_attrs()
    if user is None:
        return
    previous = cache.get(last_login_key(user.id))
    now = time.time()
    if previous:
        log(
            "logins",
            "[{date}] {ip} - {name} logged in via {via} ({browser}); "
            "previous login {minutes} min ago from {previous_ip} ({previous_browser})",
            name=user.name,
            via=via,
            browser=browser(),
            minutes=int((now - previous["at"]) // 60),
            previous_ip=previous["ip"],
            previous_browser=previous["browser"],
        )
    else:
        log(
            "logins",
            "[{date}] {ip} - {name} logged in via {via} ({browser}); first login on record",
            name=user.name,
            via=via,
            browser=browser(),
        )
    cache.set(
        last_login_key(user.id),
        {"at": now, "ip": request.remote_addr, "browser": browser()},
        timeout=LAST_LOGIN_TTL,
    )


def load(app):
    @app.before_request
    def remember_nonce_before_login():
        if request.endpoint in LOGIN_ENDPOINTS:
            g.nonce_before_login = session.get("nonce")

    @app.after_request
    def log_login(response):
        # login_user() issues a new nonce, so a changed nonce means this
        # request logged the account in (a stale login tab included).
        # No snapshot means an earlier hook refused the request before the
        # login view ran (the exam-browser rule, for one): nothing to log.
        if (
            request.endpoint in LOGIN_ENDPOINTS
            and hasattr(g, "nonce_before_login")
            and authed()
            and session.get("nonce") != g.nonce_before_login
        ):
            record_login(LOGIN_ENDPOINTS[request.endpoint])
        return response

    @app.before_request
    def enforce_single_session():
        if request.endpoint in EXEMPT_ENDPOINTS or not authed():
            return
        # An API token logs in per request (CTFd's tokens hook), so token
        # requests have no browser session to compare and are left alone.
        # An invalid token never reaches here: the hook aborts with 401.
        if authenticated_by_token():
            return
        if session_is_current():
            return
        logout_user()
        if is_api_request():
            abort(401)
        error_for(endpoint="auth.login", message=SIGNED_OUT_MESSAGE)
        return redirect(url_for("auth.login", next=request.full_path))
