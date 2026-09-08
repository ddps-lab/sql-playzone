"""SQL admission and verdict persistence, independent of judge latency."""

from datetime import datetime, timedelta
from uuid import uuid4
from threading import Lock

from flask import abort, current_app, g
from redis.exceptions import LockNotOwnedError
from sqlalchemy.exc import SQLAlchemyError

from CTFd.cache import cache, clear_challenges, clear_standings
from CTFd.exceptions.challenges import ChallengeSolveException
from CTFd.models import Challenges, Fails, Solves, db
from CTFd.utils import config, get_config
from CTFd.utils.dates import ctf_paused, ctftime
from CTFd.utils.logging import log
from CTFd.utils.user import get_current_team, get_current_user, is_admin


def require_sql_access(challenge):
    """Same state, team and prerequisite policy for page, Test and Submit."""
    if is_admin():
        return
    if challenge.state == "hidden":
        abort(404)
    if challenge.state == "locked":
        abort(403)
    user = get_current_user()
    if config.is_teams_mode() and get_current_team() is None:
        abort(403)
    if challenge.requirements:
        prerequisites = set(challenge.requirements.get("prerequisites", []))
        existing = {cid for (cid,) in db.session.query(Challenges.id).all()}
        solved = {
            cid
            for (cid,) in db.session.query(Solves.challenge_id)
            .filter_by(account_id=user.account_id)
            .all()
        }
        if not solved >= prerequisites.intersection(existing):
            abort(403)


def reply(status, message, code=200):
    return {"success": True, "data": {"status": status, "message": message}}, code


class LocalExecutionLock:
    """Single-process test/development cache; production uses Redis's lock."""

    _guard = Lock()

    def __init__(self, key):
        self.key, self.token = key, uuid4().hex

    def acquire(self, blocking=False):
        with self._guard:
            # SimpleCache leaves expired entries until a later pruning pass.
            if cache.get(self.key) is None:
                cache.delete(self.key)
            return cache.add(self.key, self.token, timeout=30)

    def owned(self):
        return cache.get(self.key) == self.token

    def release(self):
        with self._guard:
            if self.owned():
                cache.delete(self.key)


def execution_lock(account_id):
    key = f"sql_attempt_lock_{account_id}"
    backend = cache.cache
    if current_app.config["CACHE_TYPE"].lower() in ("redis", "rediscache"):
        # redis-py uses SET NX EX and an atomic owner-token check on release.
        # An expired worker must never delete the next worker's lease.
        return backend._write_client.lock(backend.key_prefix + key, timeout=30)
    return LocalExecutionLock(key)


def submit_sql(challenge, request, record_execute):
    from CTFd.plugins.sql_challenges import SQLChallengeType

    received_at = datetime.utcnow()
    in_time = ctftime()
    data = request.form or request.get_json()
    is_test = data.get("test", False)
    if not isinstance(is_test, bool):
        return reply("invalid", "test must be a boolean", 400)
    submission = data.get("submission", "")
    if not isinstance(submission, str) or not submission.strip():
        return reply("invalid", "Please provide a SQL query", 400)
    require_sql_access(challenge)
    if ctf_paused():
        return reply("paused", "Submissions and Test runs are paused", 403)
    if not is_test:
        if not in_time and not is_admin():
            return reply("closed", "Submissions are closed", 403)
        if challenge.deadline_utc and received_at > challenge.deadline_utc:
            return reply("closed", "Submission deadline has passed", 403)

    user, team = get_current_user(), get_current_team()
    # Test and Submit share an account-wide lock; switching problems cannot
    # bypass it. The judge HTTP timeout is 10s, shorter than this lease.
    lock = execution_lock(user.account_id)
    if not lock.acquire(blocking=False):
        return reply(
            "ratelimited", "Another query is being processed. Try again shortly.", 429
        )
    try:
        # Bound execution traffic separately from graded wrong attempts.
        # An ungraded failure consumes neither max_attempts nor wrong-answer KPM.
        budget_key = f"sql_execution_budget_{user.account_id}_{int(received_at.timestamp()) // 60}"
        count = cache.inc(budget_key)
        cache.expire(budget_key, 120)
        if count > 60:
            return reply(
                "ratelimited", "Too many query requests. Try again in a minute.", 429
            )
        solved = Solves.query.filter_by(
            account_id=user.account_id, challenge_id=challenge.id
        ).first()
        max_tries = challenge.max_attempts or 0
        failures = Fails.query.filter_by(
            account_id=user.account_id, challenge_id=challenge.id
        )
        behavior = get_config("max_attempts_behavior", "lockout")
        timeout = int(get_config("max_attempts_timeout", 300))
        if behavior == "timeout":
            failures = failures.filter(
                Fails.date >= received_at - timedelta(seconds=timeout)
            )
        fails = failures.count()
        if not is_test and not solved:
            if max_tries > 0 and fails >= max_tries:
                if behavior == "timeout":
                    oldest = failures.order_by(Fails.date.asc()).first()
                    remaining = max(
                        1,
                        int(
                            (
                                oldest.date + timedelta(seconds=timeout) - received_at
                            ).total_seconds()
                        )
                        + 1,
                    )
                    return reply(
                        "ratelimited",
                        f"Not accepted. Try again in {remaining} seconds",
                        429,
                    )
                return reply(
                    "ratelimited", "Not accepted. You have 0 tries remaining", 403
                )
            recent = (
                Fails.query.filter_by(account_id=user.account_id)
                .filter(Fails.date >= received_at - timedelta(seconds=60))
                .count()
            )
            if recent >= int(get_config("incorrect_submissions_per_min", 10)):
                return reply(
                    "ratelimited",
                    "Too many incorrect submissions. Try again in a minute.",
                    429,
                )

        response = SQLChallengeType.attempt(challenge, request)
        status, message = response.status, response.message
        if is_test:
            record_execute(challenge, submission, status, message)
            return reply(status, message)
        if status not in ("correct", "incorrect"):
            return reply(status, message)
        if solved:
            return reply(
                "already_solved",
                "You already solved this challenge. Your recorded score is unchanged.",
            )

        # Preserve admission time in the stored grade. Never re-check the clock
        # after a slow judge: it would silently discard an accepted submission.
        if not lock.owned():
            return reply(
                "error",
                "The submission lease expired. No verdict was saved. Please retry.",
                503,
            )
        g.submission_received_at = received_at
        try:
            if status == "correct":
                SQLChallengeType.solve(user, team, challenge, request)
            else:
                SQLChallengeType.fail(user, team, challenge, request)
        except ChallengeSolveException:
            if Solves.query.filter_by(
                account_id=user.account_id, challenge_id=challenge.id
            ).first():
                return reply("already_solved", "You already solved this challenge.")
            return reply(
                "error",
                "The result could not be saved. Please retry; no verdict is confirmed.",
                503,
            )
        except SQLAlchemyError:
            db.session.rollback()
            # A storage failure must never be reported as a saved correct answer.
            return reply(
                "error",
                "The result could not be saved. Please retry; no verdict is confirmed.",
                503,
            )
        finally:
            g.pop("submission_received_at", None)
        clear_standings()
        clear_challenges()
        log(
            "submissions",
            "[{date}] {name} submitted {submission} on {challenge_id} [{status}]",
            name=user.name,
            submission=submission.encode("utf-8"),
            challenge_id=challenge.id,
            status=status.upper(),
        )
        if status == "incorrect" and max_tries > 0:
            message += f" You have {max(0, max_tries - fails - 1)} tries remaining."
        return reply(status, message)
    finally:
        try:
            lock.release()
        except LockNotOwnedError:
            pass
