"""Explain ungraded failures without changing verdicts or exposing private SQL."""

import re

from flask import current_app

from CTFd.plugins.challenges import ChallengeResponse


def grading_failure(prefix, request_id, reason, detail, kind="system", mysql_number=None,
                    sql_state=None, deadline_exceeded=False, user_id=None, challenge_id=None):
    number = mysql_number if type(mysql_number) is int and 1000 <= mysql_number <= 65535 else None
    state = sql_state if isinstance(sql_state, str) and re.fullmatch(r"[A-Z0-9]{5}", sql_state) else None
    current_app.logger.error(
        "SQL grading failure request_id=%s user_id=%s challenge_id=%s reason=%s kind=%r mysql_number=%s sql_state=%s deadline_exceeded=%s detail=%r",
        request_id, user_id, challenge_id, reason, kind, number, state, deadline_exceeded, str(detail)[:4096],
    )
    # Keep transport distinctions in operator logs. Students need a different
    # action only for a problem error, known engine failure or confirmed deadline.
    if kind == "problem":
        message = "Problem configuration error. The problem data or reference query could not be evaluated. No attempt was deducted. Contact course staff with this reference."
    elif number in (1030, 1034):
        diagnostic = f"MySQL {number}" + (f", SQLSTATE {state}" if state else "")
        message = f"MySQL engine failure ({diagnostic}). Your answer was not graded. No attempt was deducted. Contact course staff with this reference."
    elif deadline_exceeded:
        message = "Grading time limit reached. Your answer was not graded. No attempt was deducted. Repeating the same query may reach the same limit. Contact course staff if this persists."
    else:
        message = "Grading is temporarily unavailable. No attempt was deducted. Please retry; if this persists, contact course staff."
    return ChallengeResponse(status="error", message=f"{prefix}{message} [Reference: {request_id}]")
