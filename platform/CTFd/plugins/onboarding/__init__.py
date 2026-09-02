"""Onboarding for accounts created through Google OAuth.

Google login only admits course members. Before such an account can use the
site its owner picks a user name and a password here, so later logins go
through the normal login form instead of another Google round-trip. The gate
is a request hook in the style of CTFd's own ``change_password`` hook.
"""

from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_babel import lazy_gettext as _l
from wtforms import PasswordField, StringField
from wtforms.validators import InputRequired

from CTFd.cache import clear_standings
from CTFd.forms import BaseForm
from CTFd.forms.fields import SubmitField
from CTFd.forms.users import attach_custom_user_fields, build_custom_user_fields
from CTFd.models import UserFieldEntries, UserFields, Users, db
from CTFd.utils import get_config, validators
from CTFd.utils.decorators import authed_only, ratelimit
from CTFd.utils.logging import log
from CTFd.utils.security.auth import update_user
from CTFd.utils.user import authed, get_current_user, get_current_user_attrs

# auth.google_callback stores the session nonce it logged in with under this
# key. A later form login issues a new nonce, so the marker only matches the
# session that Google actually authenticated.
GOOGLE_LOGIN_SESSION_KEY = "google_login_nonce"
# Set once the page has been offered to a Google-authenticated session, so a
# student who already has a password sees it once per Google login, not on
# every visit to the challenge list.
ONBOARDING_OFFERED_SESSION_KEY = "onboarding_offered_nonce"
GOOGLE_OAUTH_ID_PREFIX = "google_"

# Requests that must keep working while onboarding is pending.
EXEMPT_ENDPOINTS = {
    "onboarding.index",
    "auth.logout",
    "views.themes",
    "views.themes_beta",
    "views.files",
    "views.healthcheck",
    "static",
}

# Where auth.google_callback lands a user after login (users and teams mode).
LANDING_ENDPOINTS = {"challenges.listing", "teams.private"}

NAME_MAX_LENGTH = 128
PASSWORD_MAX_LENGTH = 128


def logged_in_with_google():
    marker = session.get(GOOGLE_LOGIN_SESSION_KEY)
    return marker is not None and marker == session.get("nonce")


def onboarding_pending(user_id):
    """Google-created accounts have no password until onboarding is done."""
    return db.session.query(Users.password).filter_by(id=user_id).scalar() is None


def OnboardingForm(user_id, *args, **kwargs):
    password_min_length = int(get_config("password_min_length", default=0))
    password_description = _l("Password used to log into your account")
    if password_min_length:
        password_description += _l(
            f" (Must be at least {password_min_length} characters)"
        )

    class _OnboardingForm(BaseForm):
        name = StringField(
            _l("User Name"),
            description=_l("Shown on the scoreboard. Pick any name you like."),
            validators=[InputRequired()],
            render_kw={"autofocus": True},
        )
        password = PasswordField(
            _l("Password"),
            description=password_description,
            validators=[InputRequired()],
        )
        submit = SubmitField(_l("Submit"))

        @property
        def extra(self):
            return build_custom_user_fields(
                self,
                include_entries=True,
                field_entries_kwargs={"user_id": user_id},
                blacklisted_items=(),
            )

    attach_custom_user_fields(_OnboardingForm)
    return _OnboardingForm(*args, **kwargs)


def validate_submission(user, name, password, include_fields):
    """Same rules as auth.register, applied to an existing account.

    Custom fields are collected only during the first onboarding. A later
    password reset must not touch them: the settings API refuses edits to
    fields marked non-editable, and this page should not offer a way around.
    """
    errors = []

    if len(name) == 0:
        errors.append(_l("Pick a longer user name"))
    elif len(name) > NAME_MAX_LENGTH:
        errors.append(_l("Pick a shorter user name"))
    if validators.validate_email(name) is True:
        errors.append(_l("Your user name cannot be an email address"))
    if Users.query.filter(Users.name == name, Users.id != user.id).first():
        errors.append(_l("That user name is already taken"))
    if (
        user.password is not None
        and name != user.name
        and get_config("prevent_name_change")
    ):
        errors.append(_l("Name changes are disabled"))

    password_min_length = int(get_config("password_min_length", default=0))
    if len(password) == 0:
        errors.append(_l("Pick a longer password"))
    elif password_min_length and len(password) < password_min_length:
        errors.append(_l(f"Password must be at least {password_min_length} characters"))
    elif len(password) > PASSWORD_MAX_LENGTH:
        errors.append(_l("Pick a shorter password"))

    entries = {}
    for field in UserFields.query.all() if include_fields else ():
        value = request.form.get(f"fields[{field.id}]", "").strip()
        if field.required is True and value == "":
            errors.append(_l("Please provide all required fields"))
            break
        entries[field.id] = bool(value) if field.field_type == "boolean" else value

    return errors, entries


def complete_onboarding(user, name, password, entries):
    user.name = name
    user.password = password  # hashed by the Users model validator
    for field_id, value in entries.items():
        entry = UserFieldEntries.query.filter_by(
            field_id=field_id, user_id=user.id
        ).first()
        if entry is None:
            entry = UserFieldEntries(field_id=field_id, user_id=user.id)
            db.session.add(entry)
        entry.value = value
    db.session.commit()

    # The session hash is derived from the password; refresh it so the new
    # password does not log the user out.
    update_user(user)
    clear_standings()


def load(app):
    blueprint = Blueprint(
        "onboarding", __name__, template_folder="templates", url_prefix="/onboarding"
    )

    @blueprint.route("/", methods=["GET", "POST"])
    @authed_only
    @ratelimit(method="POST", limit=10, interval=5)
    def index():
        user = get_current_user()
        pending = user.password is None
        if not pending and not logged_in_with_google():
            # Accounts that already have a password change it in Settings,
            # which asks for the current password first.
            return redirect(url_for("views.settings"))
        session[ONBOARDING_OFFERED_SESSION_KEY] = session.get("nonce")

        errors = []
        name = user.name
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            password = request.form.get("password", "").strip()
            errors, entries = validate_submission(
                user, name, password, include_fields=pending
            )
            if not errors:
                complete_onboarding(user, name, password, entries)
                log(
                    "registrations",
                    format="[{date}] {ip} - {name} completed onboarding with {email}",
                    name=user.name,
                    email=user.email,
                )
                db.session.close()
                return redirect(url_for("challenges.listing"))

        return render_template(
            "onboarding.html",
            form=OnboardingForm(user.id),
            errors=errors,
            name=name,
            email=user.email,
            pending=pending,
        )

    app.register_blueprint(blueprint)

    @app.before_request
    def require_onboarding():
        if request.endpoint in EXEMPT_ENDPOINTS or not authed():
            return
        user = get_current_user_attrs()
        if user is None or user.type == "admin":
            return
        if not str(user.oauth_id or "").startswith(GOOGLE_OAUTH_ID_PREFIX):
            return
        if onboarding_pending(user.id):
            return redirect(url_for("onboarding.index"))
        # Google login is the way to set a new password, so show the page
        # once when such a session first reaches its landing page.
        if (
            request.endpoint in LANDING_ENDPOINTS
            and logged_in_with_google()
            and session.get(ONBOARDING_OFFERED_SESSION_KEY) != session.get("nonce")
        ):
            session[ONBOARDING_OFFERED_SESSION_KEY] = session.get("nonce")
            return redirect(url_for("onboarding.index"))
