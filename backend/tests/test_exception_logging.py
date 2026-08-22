from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy.exc import OperationalError
from starlette.requests import Request

from app import main


def _request(path: str = "/api/social-media/list/sync") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "query_string": b"",
            "scheme": "https",
            "server": ("example.test", 443),
            "client": ("127.0.0.1", 12345),
        }
    )


class ExceptionLoggingTest(unittest.IsolatedAsyncioTestCase):
    async def test_sqlalchemy_handler_logs_request_and_exception(self) -> None:
        error = OperationalError(
            "SELECT task_queue.dedupe_key FROM task_queue",
            {},
            Exception("column task_queue.dedupe_key does not exist"),
        )
        with patch.object(main.logger, "exception") as log_exception:
            response = await main.sqlalchemy_exception_handler(_request(), error)

        self.assertEqual(response.status_code, 503)
        log_exception.assert_called_once()
        self.assertEqual(log_exception.call_args.args[1:3], ("POST", "/api/social-media/list/sync"))

    async def test_unexpected_handler_logs_request_and_exception(self) -> None:
        error = RuntimeError("unexpected")
        with patch.object(main.logger, "exception") as log_exception:
            response = await main.unexpected_exception_handler(_request("/api/test"), error)

        self.assertEqual(response.status_code, 500)
        log_exception.assert_called_once()
        self.assertEqual(log_exception.call_args.args[1:3], ("POST", "/api/test"))


if __name__ == "__main__":
    unittest.main()
