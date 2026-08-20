from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.routers import social_media


class OAuthCallbackAndFrontendCacheTest(unittest.IsolatedAsyncioTestCase):
    def test_oauth_callback_does_not_require_sparkling_session(self) -> None:
        config = SimpleNamespace(oauth_redirect_uri="https://example.test/api/social-media/youtube/oauth/callback")
        client = TestClient(app)
        with patch.object(social_media, "load_social_media_config", return_value=config):
            response = client.get(
                "/api/social-media/youtube/oauth/callback?error=access_denied",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 307)
        self.assertEqual(
            response.headers["location"],
            "https://example.test/settings?section=social-media&youtube=error",
        )

    async def test_index_is_not_cached_and_assets_are_immutable(self) -> None:
        import app.main as main

        with tempfile.TemporaryDirectory() as directory:
            frontend = Path(directory)
            (frontend / "assets").mkdir()
            (frontend / "index.html").write_text("index", encoding="utf-8")
            (frontend / "assets" / "app-hash.js").write_text("javascript", encoding="utf-8")
            with patch.object(main, "_frontend_dir", frontend):
                index_response = await main.serve_frontend("")
                asset_response = await main.serve_frontend("assets/app-hash.js")

        self.assertIn("no-cache", index_response.headers["cache-control"])
        self.assertIn("immutable", asset_response.headers["cache-control"])

    async def test_missing_asset_does_not_fall_back_to_index(self) -> None:
        import app.main as main

        with tempfile.TemporaryDirectory() as directory:
            frontend = Path(directory)
            (frontend / "index.html").write_text("index", encoding="utf-8")
            with patch.object(main, "_frontend_dir", frontend):
                with self.assertRaisesRegex(Exception, "Not found"):
                    await main.serve_frontend("assets/missing-hash.js")


if __name__ == "__main__":
    unittest.main()
