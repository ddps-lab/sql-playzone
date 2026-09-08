"""One active session per student account, checked on every request, with a login trail.

Logging in stores the session's nonce as the account's active nonce in
the cache, and the fork's ``get_current_user()`` signs out any other
session it sees. That check only runs on pages that load the full user,
so an older session could still open the scoreboard or a challenge page
after a newer login. The request hook here runs the same check for
every request. Both apply only while the "one session per student"
switch on the Exam Mode page is on, and never to admins.

Each successful login records the account's user_id and login_id, browser,
and previous login. The stable user_id links these records to SQL execution
and behavior events, including accounts with the same display name.
"""

import json
import time

from flask import abort, g, redirect, request, session, url_for

from CTFd.cache import cache
from CTFd.models import Users
from CTFd.utils import get_config
from CTFd.utils.config.pages import is_public_site_info
from CTFd.utils.helpers import error_for
from CTFd.utils.logging import log, user_log_fields
from CTFd.utils.security.auth import logout_user
from CTFd.utils.user import authed, get_current_user_attrs, get_ip

# Requests that need no session check: leaving, static files, health probes.
EXEMPT_ENDPOINTS = {
    "auth.logout",
    "views.themes",
    "views.themes_beta",
    "views.healthcheck",
    "static",
}
LOGIN_ENDPOINTS = {
    "auth.register": "registration",
    "auth.login": "form",
    "auth.google_callback": "google",
    "auth.oauth_redirect": "mlc",
}
LAST_LOGIN_TTL = 30 * 24 * 3600
# Set from the Exam Mode admin page (exam_mode plugin).
SINGLE_SESSION_CONFIG = "single_session_required"
SIGNED_OUT_MESSAGE = (
    "This account signed in from another browser, so this session was signed out."
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


def single_session_required():
    return get_config(SINGLE_SESSION_CONFIG) is True


def session_is_current():
    active_nonce = cache.get(f"user_{session['id']}_active_nonce")
    return not active_nonce or session.get("nonce") == active_nonce


def browser():
    return (request.user_agent.string or "")[:120]


def last_login_key(user_id):
    return f"user_{user_id}_last_login"


def record_login(via):
    """One line per login: browser and the previous login of the account.

    CTFd writes its own "logged in" line as well; this one reads
    "session started" so a review counts one kind of line only.
    """
    # UserAttrs has no login_id; read the current identity once per login.
    user = (
        Users.query.with_entities(Users.id, Users.login_id, Users.name)
        .filter_by(id=session.get("id"))
        .first()
    )
    if user is None:
        return
    previous = cache.get(last_login_key(user.id))
    now = time.time()
    if previous:
        log(
            "logins",
            "[{date}] {ip} - event=session_started user_id={user_id} login_id={login_id} "
            "{name} session started via {via} ({browser}); "
            "previous session {minutes} min ago from {previous_ip} ({previous_browser})",
            via=via,
            browser=json.dumps(browser(), ensure_ascii=False),
            minutes=int((now - previous["at"]) // 60),
            previous_ip=previous["ip"],
            previous_browser=json.dumps(previous["browser"], ensure_ascii=False),
            **user_log_fields(user),
        )
    else:
        log(
            "logins",
            "[{date}] {ip} - event=session_started user_id={user_id} login_id={login_id} "
            "{name} session started via {via} ({browser}); first session on record",
            via=via,
            browser=json.dumps(browser(), ensure_ascii=False),
            **user_log_fields(user),
        )
    cache.set(
        last_login_key(user.id),
        # the same resolved address CTFd's log lines use (proxies considered)
        {"at": now, "ip": get_ip(), "browser": browser()},
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
        if (
            is_public_site_info()
            or request.endpoint in EXEMPT_ENDPOINTS
            or not authed()
        ):
            return
        if not single_session_required():
            return
        # An API token logs in per request (CTFd's tokens hook), so token
        # requests have no browser session to compare and are left alone.
        # An invalid token never reaches here: the hook aborts with 401.
        if authenticated_by_token():
            return
        # Admins may be signed in from several places (two TAs on one
        # account, or a token script beside the browser).
        user = get_current_user_attrs()
        if user is not None and user.type == "admin":
            return
        if session_is_current():
            return
        logout_user()
        if is_api_request():
            abort(401)
        error_for(endpoint="auth.login", message=SIGNED_OUT_MESSAGE)
        return redirect(url_for("auth.login", next=request.full_path))
