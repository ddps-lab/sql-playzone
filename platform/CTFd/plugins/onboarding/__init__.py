"""Onboarding for accounts created through Google OAuth.

Google login only admits course members. Before such an account can use the
site its owner picks a user name and a password here and accepts the terms
of service, so later logins go through the normal login form instead of
another Google round-trip. The gate is a request hook in the style of CTFd's
own ``change_password`` hook.
"""

import unicodedata
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_babel import lazy_gettext as _l
from markupsafe import Markup
from wtforms import PasswordField, StringField
from wtforms.validators import InputRequired

from CTFd.cache import clear_config, clear_standings
from CTFd.forms import BaseForm
from CTFd.forms.fields import SubmitField
from CTFd.forms.users import attach_custom_user_fields, build_custom_user_fields
from CTFd.models import Files, UserFieldEntries, UserFields, Users, db
from CTFd.utils import get_config, set_config, validators
from CTFd.utils.config.pages import build_markdown
from CTFd.utils.decorators import authed_only, ratelimit
from CTFd.utils.logging import log
from CTFd.utils.security.auth import update_user
from CTFd.utils.user import authed, get_current_user, get_current_user_attrs

# auth.google_callback stores the session nonce it logged in with under this
# key. A later form login issues a new nonce, so the marker only matches the
# session that Google actually authenticated.
GOOGLE_LOGIN_SESSION_KEY = "google_login_nonce"
# Set once this page has been completed in a Google-authenticated session.
# Until then such a session cannot go anywhere else: signing in with Google
# again means "set a new password", and it must not be skipped.
ONBOARDING_DONE_SESSION_KEY = "onboarding_done_nonce"
GOOGLE_OAUTH_ID_PREFIX = "google_"

# Requests that must keep working while onboarding is pending.
EXEMPT_ENDPOINTS = {
    "onboarding.index",
    "auth.logout",
    "views.themes",
    "views.themes_beta",
    "views.healthcheck",
    "static",
}

# Consent to the terms is recorded as a required, non-editable boolean user
# field: the same CTFd mechanism the student_fields plugin uses for the
# student ID, so it shows up in the admin user view and exports.
TERMS_FIELD_NAME = "Terms of Service"
TERMS_FIELD_DESCRIPTION = "I have read and agree to the Terms of Service above."
TERMS_TEXT_PATH = Path(__file__).with_name("terms.md")

# What a checked boolean field submits (WTForms sends "y"); anything else,
# including "false" or "0" from a hand-made request, is not consent.
AFFIRMATIVE_VALUES = {"y", "yes", "true", "on", "1"}

# The email address is the link to the Google account and the login name;
# students cannot change it (admins can, in the admin panel).
EMAIL_LOCKED_MESSAGE = (
    "Your email address comes from your HYU Google account and cannot be changed here."
)

# Uploaded files any page may need: logo, banner, page images. Challenge and
# solution attachments are not among them.
SITE_ASSET_FILE_TYPES = ("standard", "page")

NAME_MAX_LENGTH = 128
PASSWORD_MAX_LENGTH = 128
# A minimal password rule: long enough and not a bare number or bare word.
# CTFd's own password_min_length config is raised to this floor so the
# settings page enforces the same length.
PASSWORD_MIN_LENGTH = 8


def request_is_exempt():
    if request.endpoint in EXEMPT_ENDPOINTS:
        return True
    if request.endpoint == "views.files":
        # Uploaded files serve both site assets, which this page needs, and
        # challenge or solution attachments, which stay gated like every
        # other challenge request.
        upload = Files.query.filter_by(location=request.view_args.get("path")).first()
        return upload is None or upload.type in SITE_ASSET_FILE_TYPES
    return False


def logged_in_with_google():
    marker = session.get(GOOGLE_LOGIN_SESSION_KEY)
    return marker is not None and marker == session.get("nonce")


def onboarding_done_in_session():
    return session.get(ONBOARDING_DONE_SESSION_KEY) == session.get("nonce")


def password_min_length():
    """CTFd's configured minimum, raised to the floor if it is below it.

    Raising the stored value too keeps the settings page and CTFd's own
    reset flow on the same rule. Checked here as well as at startup because
    a CTFd import replaces the configs table without restarting the app.
    """
    configured = int(get_config("password_min_length", default=0) or 0)
    if configured >= PASSWORD_MIN_LENGTH:
        return configured
    presets = current_app.config.get("PRESET_CONFIGS") or {}
    if "password_min_length" not in presets:
        set_config("password_min_length", PASSWORD_MIN_LENGTH)
        clear_config()
    # A preset below the floor always wins in get_config and cannot be
    # raised from here; this plugin's own pages enforce the floor regardless.
    return PASSWORD_MIN_LENGTH


def ensure_password_policy(app):
    with app.app_context():
        password_min_length()


def onboarding_pending(user_id):
    """Google-created accounts have no password until onboarding is done."""
    return db.session.query(Users.password).filter_by(id=user_id).scalar() is None


def terms_field():
    """The consent field, created on first use if it does not exist.

    Created lazily as well as at startup: a CTFd import replaces the
    fields table while the app keeps running, and without the field every
    imported account would pass the consent gate. Workers starting at the
    same time may each create one, so duplicates are folded into the first.
    """
    fields = (
        UserFields.query.filter_by(name=TERMS_FIELD_NAME).order_by(UserFields.id).all()
    )
    if not fields:
        db.session.add(
            UserFields(
                name=TERMS_FIELD_NAME,
                description=TERMS_FIELD_DESCRIPTION,
                field_type="boolean",
                required=True,
                public=False,
                editable=False,
            )
        )
        db.session.commit()
        fields = (
            UserFields.query.filter_by(name=TERMS_FIELD_NAME)
            .order_by(UserFields.id)
            .all()
        )
    field = fields[0]
    for duplicate in fields[1:]:
        # A user may have an entry under both; keep one row and keep consent.
        for entry in UserFieldEntries.query.filter_by(field_id=duplicate.id).all():
            kept = UserFieldEntries.query.filter_by(
                field_id=field.id, user_id=entry.user_id
            ).first()
            if kept is None:
                entry.field_id = field.id
                continue
            if is_affirmative(entry.value) and not is_affirmative(kept.value):
                kept.value = True
            db.session.delete(entry)
        db.session.delete(duplicate)
    # A same-name field from an older installation is adopted, but it must
    # have this shape or consent could be stored as text and never count.
    expected = {
        "description": TERMS_FIELD_DESCRIPTION,
        "field_type": "boolean",
        "required": True,
        "public": False,
        "editable": False,
    }
    changed = False
    for attribute, value in expected.items():
        if getattr(field, attribute) != value:
            setattr(field, attribute, value)
            changed = True
    if len(fields) > 1 or changed:
        db.session.commit()
    return field


def is_affirmative(value):
    # Entries written while the field was still a text field hold "y".
    return value is True or str(value).lower() in AFFIRMATIVE_VALUES


def terms_missing(user_id):
    """True until this account has said yes to the terms.

    An entry that exists but holds False (an import, an admin edit) is not
    consent, so the value is checked rather than the row's existence.
    """
    entry = UserFieldEntries.query.filter_by(
        field_id=terms_field().id, user_id=user_id
    ).first()
    return entry is None or not is_affirmative(entry.value)


def terms_text():
    """CTFd's tos_text, seeded with the plugin's draft when nothing is set.

    Admins edit the text in Config > Legal; the seed never overwrites it.
    Seeded lazily as well as at startup for the same import reason.
    """
    text = get_config("tos_text")
    if not text and not get_config("tos_url"):
        text = TERMS_TEXT_PATH.read_text(encoding="utf-8")
        set_config("tos_text", text)
        clear_config()
    return text


def ensure_terms(app):
    """Seed the terms text and the consent field at startup."""
    with app.app_context():
        terms_text()
        terms_field()


def terms_html():
    """The terms rendered for the onboarding page, or None when hosted elsewhere."""
    if get_config("tos_url"):
        return None
    # Trusted admin content, rendered the way views.tos renders it.
    return Markup(build_markdown(terms_text()))


def OnboardingForm(user_id, *args, **kwargs):
    password_description = _l(
        f"Password used to log into your account. At least {password_min_length()} "
        "characters with both a letter and a digit."
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
        password_confirm = PasswordField(
            _l("Confirm Password"),
            description=_l("Type the same password again."),
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


def validate_password(password, password_confirm):
    errors = []
    if len(password) == 0:
        errors.append(_l("Pick a longer password"))
    elif len(password) < password_min_length():
        errors.append(
            _l(f"Password must be at least {password_min_length()} characters")
        )
    elif len(password) > PASSWORD_MAX_LENGTH:
        errors.append(_l("Pick a shorter password"))
    elif not (
        any(c.isalpha() for c in password)
        # decimal digits only (Unicode Nd), matching the page's live check
        and any(unicodedata.category(c) == "Nd" for c in password)
    ):
        errors.append(_l("Password must contain both a letter and a digit"))
    if password_confirm != password:
        errors.append(_l("Passwords do not match"))
    return errors


def validate_submission(user, name, password, password_confirm, credentials, fields):
    """Same rules as auth.register, applied to an existing account.

    ``credentials`` says whether a user name and password are being set;
    ``fields`` lists the custom user fields collected on this visit.
    """
    errors = []

    if credentials:
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

        errors.extend(validate_password(password, password_confirm))

    entries = {}
    for field in fields:
        value = request.form.get(f"fields[{field.id}]", "").strip()
        if field.field_type == "boolean":
            value = value.lower() in AFFIRMATIVE_VALUES
        if field.required is True and value in ("", False):
            if field.name == TERMS_FIELD_NAME:
                errors.append(_l("Please agree to the Terms of Service to continue"))
            else:
                errors.append(_l("Please provide all required fields"))
            break
        entries[field.id] = value

    return errors, entries


def complete_onboarding(user, name, password, entries, credentials):
    if credentials:
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

    if credentials:
        # The session hash is derived from the password; refresh it so the
        # new password does not log the user out.
        update_user(user)
        clear_standings()


def load(app):
    ensure_terms(app)
    ensure_password_policy(app)

    blueprint = Blueprint(
        "onboarding", __name__, template_folder="templates", url_prefix="/onboarding"
    )

    @blueprint.route("/", methods=["GET", "POST"])
    @authed_only
    # A whole class may onboard at once from one NAT address.
    @ratelimit(method="POST", limit=30, interval=5)
    def index():
        user = get_current_user()
        # Only Google-created accounts set up local credentials here; other
        # password-less OAuth accounts keep their provider login.
        needs_password = user.password is None and str(user.oauth_id or "").startswith(
            GOOGLE_OAUTH_ID_PREFIX
        )
        # Admins are exempt from required fields, as in require_complete_profile.
        needs_terms = user.type != "admin" and terms_missing(user.id)
        if not needs_password and not needs_terms and not logged_in_with_google():
            # Accounts that already have a password change it in Settings,
            # which asks for the current password first.
            return redirect(url_for("views.settings"))

        # What this visit asks for: everything on the first visit, only the
        # terms when an existing account never accepted them, and a new
        # password when a Google-authenticated session comes back.
        if needs_password:
            mode = "setup"
            fields = UserFields.query.all()
        elif needs_terms:
            mode = "terms"
            fields = [terms_field()]
        else:
            mode = "reset"
            fields = []
        credentials = mode != "terms"

        errors = []
        name = user.name
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            password = request.form.get("password", "").strip()
            password_confirm = request.form.get("password_confirm", "").strip()
            errors, entries = validate_submission(
                user, name, password, password_confirm, credentials, fields
            )
            if not errors:
                complete_onboarding(user, name, password, entries, credentials)
                if credentials:
                    # A Google session that only gave consent still owes the
                    # password reset; the hook brings it back here for that.
                    session[ONBOARDING_DONE_SESSION_KEY] = session.get("nonce")
                actions = []
                if mode == "setup":
                    actions.append("completed onboarding")
                elif mode == "reset":
                    actions.append("set a new password")
                if entries.get(terms_field().id):
                    actions.append("accepted the terms of service")
                log(
                    "registrations",
                    format="[{date}] {ip} - {name} ({email}) {actions}",
                    name=user.name,
                    email=user.email,
                    actions=" and ".join(actions),
                )
                db.session.close()
                return redirect(url_for("challenges.listing"))

        return render_template(
            "onboarding.html",
            form=OnboardingForm(user.id),
            errors=errors,
            name=name,
            email=user.email,
            mode=mode,
            terms=terms_html() if mode != "reset" else None,
            terms_field_name=TERMS_FIELD_NAME,
            password_min_length=password_min_length(),
            password_max_length=PASSWORD_MAX_LENGTH,
        )

    app.register_blueprint(blueprint)

    @app.before_request
    def require_onboarding():
        if request_is_exempt():
            return
        # Keep the password floor in force for every password-writing flow,
        # including CTFd's own reset page right after a live import.
        password_min_length()
        if not authed():
            return
        user = get_current_user_attrs()
        if user is None or user.type == "admin":
            return
        if request.endpoint == "api.users_user_private" and request.method == "PATCH":
            data = request.get_json(silent=True) or {}
            submitted = str(data.get("email") or "").strip().lower()
            if "email" in data and submitted != str(user.email or "").lower():
                response = jsonify(
                    {"success": False, "errors": {"email": [EMAIL_LOCKED_MESSAGE]}}
                )
                response.status_code = 400
                return response
        google_account = str(user.oauth_id or "").startswith(GOOGLE_OAUTH_ID_PREFIX)
        if google_account and onboarding_pending(user.id):
            return redirect(url_for("onboarding.index"))
        # Nothing else works until the terms are accepted. CTFd's own
        # required-field check would only send the account to Settings,
        # which cannot show a non-editable field.
        if terms_missing(user.id):
            return redirect(url_for("onboarding.index"))
        # Signing in with Google again is the way to set a new password; the
        # session stays on this page until that is done.
        if logged_in_with_google() and not onboarding_done_in_session():
            return redirect(url_for("onboarding.index"))
