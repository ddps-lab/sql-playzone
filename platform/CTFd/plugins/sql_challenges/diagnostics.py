"""Public grading failure reasons; raw judge errors stay in operator logs."""

import re

from flask import current_app

from CTFd.plugins.challenges import ChallengeResponse


FAILURES = {
    "mysql_engine_error": ("MySQL engine failure", "The grading database failed internally while executing SQL.", False),
    "mysql_unsupported": ("Unsupported MySQL feature", "The grading database could not execute a SQL feature used in this evaluation.", False),
    "mysql_failure": ("MySQL execution failure", "The database reported an error that cannot be attributed to your answer.", False),
    "problem_error": ("Problem configuration error", "The problem data or reference query could not be evaluated.", False),
    "judge_busy": ("Grading service busy", "All grading workers are occupied.", True),
    "judge_timeout": ("Grading service timeout", "The grading operation exceeded its processing deadline.", True),
    "judge_connection_timeout": ("Grading connection timeout", "The grading service did not respond in time.", True),
    "judge_connection_failure": ("Grading connection failure", "The platform could not communicate with the grading service.", True),
    "judge_http_failure": ("Grading HTTP failure", "The grading service returned an unsuccessful HTTP response.", True),
    "judge_invalid_response": ("Invalid grading response", "The grading service returned an incomplete or unreadable response.", True),
    "judge_unavailable": ("Grading service failure", "The platform could not complete grading.", True),
}


def grading_failure(prefix, request_id, code, detail, mysql_number=None, sql_state=None,
                    user_id=None, challenge_id=None):
    # Never interpolate an arbitrary internal error, status, SQLSTATE or code into
    # the student message: these may contain reference SQL or server details.
    public_code = code if isinstance(code, str) and code in FAILURES else "judge_unavailable"
    number = mysql_number if type(mysql_number) is int and 1000 <= mysql_number <= 65535 else None
    state = sql_state if isinstance(sql_state, str) and re.fullmatch(r"[A-Z0-9]{5}", sql_state) else None
    current_app.logger.error(
        "SQL grading failure request_id=%s user_id=%s challenge_id=%s code=%s mysql_number=%s sql_state=%s detail=%r",
        request_id, user_id, challenge_id, public_code, number, state, str(detail)[:4096],
    )
    title, reason, retry = FAILURES[public_code]
    diagnostic = f" MySQL {number}" if number else ""
    if number and state:
        diagnostic += f", SQLSTATE {state}"
    if diagnostic:
        diagnostic += "."
    action = ("Please retry; if this persists, contact course staff." if retry
              else "Contact course staff with the reference below.")
    message = (
        f"{prefix}{title}.{diagnostic} {reason} "
        f"Your answer was not graded. No attempt was deducted. {action} "
        f"[Code: {public_code}; reference: {request_id}]"
    )
    return ChallengeResponse(status="error", message=message)
