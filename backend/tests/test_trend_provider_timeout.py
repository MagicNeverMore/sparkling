import asyncio
import time
import unittest

from app.models import Settings
from app.services.trend import collector


class TrendProviderTimeoutTest(unittest.IsolatedAsyncioTestCase):
    async def test_provider_test_returns_when_server_never_responds(self) -> None:
        previous_timeout = collector.TREND_PROVIDER_TEST_TIMEOUT_SECONDS
        collector.TREND_PROVIDER_TEST_TIMEOUT_SECONDS = 0.2
        writers: set[asyncio.StreamWriter] = set()

        async def handle(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writers.add(writer)
            try:
                await asyncio.Event().wait()
            finally:
                writers.discard(writer)
                writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        settings = Settings(
            trend_base_url=f"http://127.0.0.1:{port}/v1",
            trend_model="qwen2.5:7b",
        )

        try:
            started = time.monotonic()
            ok, _latency_ms, error = await asyncio.wait_for(
                collector.test_trend_provider(settings),
                timeout=2.0,
            )
            elapsed = time.monotonic() - started
        finally:
            collector.TREND_PROVIDER_TEST_TIMEOUT_SECONDS = previous_timeout
            for writer in list(writers):
                writer.close()
                await writer.wait_closed()
            server.close()
            await server.wait_closed()

        self.assertFalse(ok)
        self.assertIsNotNone(error)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
