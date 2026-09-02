"""One active session per account, checked on every request.

Logging in stores the session's nonce as the account's active nonce in
the cache, and the fork's ``get_current_user()`` signs out any other
session it sees. That check only runs on pages that load the full user,
so an older session could still open the scoreboard or a challenge page
after a newer login. This hook runs the same check for every request.
"""

from flask import abort, redirect, request, session, url_for

from CTFd.cache import cache
from CTFd.models import Users
from CTFd.utils import validators
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
# A session counts as active for this long after its last request. The
# active-nonce key itself lives for 30 days and survives logouts, so it
# cannot tell a live session from a stale one.
SESSION_ACTIVITY_WINDOW = 30 * 60
LOGIN_ENDPOINTS = {"auth.login", "auth.google_callback", "auth.oauth_redirect"}
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


def seen_key(user_id):
    return f"user_{user_id}_session_seen"


def mark_session_seen():
    cache.set(
        seen_key(session["id"]), session.get("nonce"), timeout=SESSION_ACTIVITY_WINDOW
    )


def forget_session():
    """On logout: no session of this account is active any more.

    Only the activity marker goes. The active nonce stays so that an older
    session cookie that was superseded remains signed out.
    """
    cache.delete(seen_key(session["id"]))


def browser():
    return (request.user_agent.string or "")[:120]


def load(app):
    @app.before_request
    def note_login_while_another_session_is_active():
        """DDPS-1303: leave a trace for the exam review, keyed by user and time.

        The login itself is logged by CTFd; this line says that another
        session was alive at that moment. The older session is signed out
        on its next request, which is logged there.
        """
        if request.endpoint != "auth.login" or request.method != "POST":
            return
        name = (request.form.get("name") or "").strip()
        if not name:
            return
        if validators.validate_email(name) is True:
            user = Users.query.filter_by(email=name).first()
        else:
            user = Users.query.filter_by(name=name).first()
        if user and cache.get(seen_key(user.id)):
            log(
                "logins",
                "[{date}] {ip} - {name} login attempt while another session is active ({browser})",
                name=user.name,
                browser=browser(),
            )

    @app.after_request
    def mark_new_login_seen(response):
        # A session counts as active from the moment it logs in, before it
        # makes any other request.
        if request.endpoint in LOGIN_ENDPOINTS and authed() and session_is_current():
            mark_session_seen()
        return response

    @app.before_request
    def enforce_single_session():
        if request.endpoint == "auth.logout" and authed() and session_is_current():
            forget_session()
            return
        if request.endpoint in EXEMPT_ENDPOINTS or not authed():
            return
        # An API token logs in per request (CTFd's tokens hook), so token
        # requests have no browser session to compare and are left alone.
        # An invalid token never reaches here: the hook aborts with 401.
        if authenticated_by_token():
            return
        if session_is_current():
            mark_session_seen()
            return
        user = get_current_user_attrs()
        log(
            "logins",
            "[{date}] {ip} - {name} signed out: the account signed in from another browser ({browser})",
            name=user.name if user else session.get("id"),
            browser=browser(),
        )
        logout_user()
        if is_api_request():
            abort(401)
        error_for(endpoint="auth.login", message=SIGNED_OUT_MESSAGE)
        return redirect(url_for("auth.login", next=request.full_path))
