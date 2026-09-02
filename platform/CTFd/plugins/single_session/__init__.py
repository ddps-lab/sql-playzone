"""One active session per account, checked on every request.

Logging in stores the session's nonce as the account's active nonce in
the cache, and the fork's ``get_current_user()`` signs out any other
session it sees. That check only runs on pages that load the full user,
so an older session could still open the scoreboard or a challenge page
after a newer login. This hook runs the same check for every request.
"""

from flask import abort, redirect, request, session, url_for

from CTFd.cache import cache
from CTFd.utils.helpers import error_for
from CTFd.utils.security.auth import logout_user
from CTFd.utils.user import authed

# Requests that need no session check: leaving, static files, health probes.
EXEMPT_ENDPOINTS = {
    "auth.logout",
    "views.themes",
    "views.themes_beta",
    "views.healthcheck",
    "static",
}
SIGNED_OUT_MESSAGE = (
    "This account signed in from another browser, so this session was signed out. "
    "다른 브라우저에서 로그인되어 이 세션은 로그아웃되었습니다."
)


def is_api_request():
    # The API blueprint, not the URL prefix: APPLICATION_ROOT may be set.
    return request.is_json or str(request.endpoint or "").startswith("api.")


def session_is_current():
    active_nonce = cache.get(f"user_{session['id']}_active_nonce")
    return not active_nonce or session.get("nonce") == active_nonce


def load(app):
    @app.before_request
    def enforce_single_session():
        if request.endpoint in EXEMPT_ENDPOINTS or not authed():
            return
        # An API token logs in per request (CTFd's tokens hook), so token
        # requests have no browser session to compare and are left alone.
        if request.headers.get("Authorization"):
            return
        if session_is_current():
            return
        logout_user()
        if is_api_request():
            abort(401)
        error_for(endpoint="auth.login", message=SIGNED_OUT_MESSAGE)
        return redirect(url_for("auth.login", next=request.full_path))
