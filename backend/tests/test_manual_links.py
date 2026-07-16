from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import ThoughtAtom, ThoughtLink
from app.routers import links


class ManualLinkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all(
                [
                    ThoughtAtom(id="atom-a", content="A", status="inbox", version=1),
                    ThoughtAtom(id="atom-b", content="B", status="inbox", version=1),
                ]
            )
            session.commit()

    def tearDown(self) -> None:
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    async def test_create_manual_link_is_confirmed_and_idempotent_in_reverse(self) -> None:
        broadcast = AsyncMock()
        with patch.object(links.manager, "broadcast", broadcast):
            first = await links.create_manual_link(
                links.ManualLinkCreate(from_atom_id="atom-a", to_atom_id="atom-b"),
                Session(self.engine),
            )
            second = await links.create_manual_link(
                links.ManualLinkCreate(from_atom_id="atom-b", to_atom_id="atom-a"),
                Session(self.engine),
            )

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.link_type, "manual")
        self.assertEqual(first.source, "user")
        self.assertTrue(first.user_confirmed)
        self.assertFalse(first.user_ignored)
        with Session(self.engine) as session:
            self.assertEqual(session.query(ThoughtLink).count(), 1)
        self.assertEqual(broadcast.await_count, 2)

    async def test_create_manual_link_restores_existing_suggestion(self) -> None:
        with Session(self.engine) as session:
            session.add(
                ThoughtLink(
                    id="suggestion",
                    from_atom_id="atom-b",
                    to_atom_id="atom-a",
                    link_type="semantic",
                    confidence=0.8,
                    source="ai_suggested",
                    user_confirmed=False,
                    user_ignored=True,
                )
            )
            session.commit()

        with patch.object(links.manager, "broadcast", AsyncMock()):
            result = await links.create_manual_link(
                links.ManualLinkCreate(from_atom_id="atom-a", to_atom_id="atom-b"),
                Session(self.engine),
            )

        self.assertEqual(result.id, "suggestion")
        self.assertEqual(result.source, "user")
        self.assertTrue(result.user_confirmed)
        self.assertFalse(result.user_ignored)

    async def test_create_manual_link_rejects_self_link(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await links.create_manual_link(
                links.ManualLinkCreate(from_atom_id="atom-a", to_atom_id="atom-a"),
                Session(self.engine),
            )
        self.assertEqual(raised.exception.status_code, 400)

    async def test_create_manual_link_rejects_missing_target(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await links.create_manual_link(
                links.ManualLinkCreate(from_atom_id="atom-a", to_atom_id="missing"),
                Session(self.engine),
            )
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
