"""Public notices managed through CTFd's Config > Legal settings."""

from pathlib import Path

from CTFd.cache import clear_config
from CTFd.utils import get_config, set_config


def load(app):
    # Preserve administrator-written notices and externally hosted policies.
    with app.app_context():
        for key, filename in (("tos", "terms.md"), ("privacy", "privacy.md")):
            if not get_config(f"{key}_text") and not get_config(f"{key}_url"):
                text = Path(__file__).with_name(filename).read_text(encoding="utf-8")
                set_config(f"{key}_text", text)
        clear_config()
