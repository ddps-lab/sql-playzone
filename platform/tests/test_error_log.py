"""Request exceptions must reach a file the CloudWatch agent ships."""

import logging
import re
import sys

from CTFd.config import TestingConfig
from tests.helpers import create_ctfd, destroy_ctfd


def test_request_exceptions_reach_the_shipped_error_log(tmp_path):
    class Config(TestingConfig):
        LOG_FOLDER = str(tmp_path)

    app = create_ctfd(config=Config)
    path = tmp_path / "app-errors.log"
    try:
        with app.test_request_context("/login", method="POST"):
            try:
                raise RuntimeError("boom")
            except RuntimeError:
                app.log_exception(sys.exc_info())
            logging.getLogger("logins").info("routine login line")
        for handler in logging.getLogger().handlers:
            handler.flush()
        text = path.read_text()
        # The record starts with the timestamp the agent's
        # multi_line_start_pattern expects, and the traceback follows it.
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ERROR \[CTFd\] Exception on /login \[POST\]", text)
        assert "Traceback (most recent call last)" in text
        assert "RuntimeError: boom" in text
        assert "routine login line" not in text
    finally:
        root = logging.getLogger()
        for handler in list(root.handlers):
            if getattr(handler, "baseFilename", "") == str(path):
                root.removeHandler(handler)
                handler.close()
        destroy_ctfd(app)
