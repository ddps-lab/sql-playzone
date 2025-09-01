from CTFd.constants.options import (
    AccountVisibilityTypes,
    ChallengeVisibilityTypes,
    RegistrationVisibilityTypes,
    ScoreVisibilityTypes,
    UserModeTypes,
)
from CTFd.constants.themes import DEFAULT_THEME

DEFAULTS = {
    # General Settings
    "ctf_name": "SQL PlayZone",
    "user_mode": UserModeTypes.USERS,
    # Visual/Style Settings
    "ctf_theme": DEFAULT_THEME,
    # Visibility Settings
    "challenge_visibility": ChallengeVisibilityTypes.PRIVATE,
    "registration_visibility": RegistrationVisibilityTypes.GOOGLE_OAUTH_ONLY,
    "score_visibility": ScoreVisibilityTypes.PUBLIC,
    "account_visibility": AccountVisibilityTypes.PUBLIC,
    # Localization Settings
    "default_locale": "en",
}
