import json
import logging
import logging.handlers
import time

from flask import session

from CTFd.utils.user import get_ip


def user_log_fields(user):
    """Use the authenticated account; quote text so it stays on one log line."""
    return {
        "user_id": user.id,
        "login_id": json.dumps(user.login_id, ensure_ascii=False),
        "name": json.dumps(user.name, ensure_ascii=False),
    }


def log(logger, format, **kwargs):
    logger = logging.getLogger(logger)
    props = {
        "id": session.get("id"),
        "date": time.strftime("%m/%d/%Y %X"),
        "ip": get_ip(),
    }
    props.update(kwargs)
    msg = format.format(**props)
    logger.info(msg)
