"""Run against a disposable PostgreSQL DB with unittest (no production fixtures)."""
import importlib.util
import asyncio
import hashlib
import os
from pathlib import Path
import threading
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI, HTTPException
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.models.user_role import UserRole
from app.models.conversation import Conversation, ConversationTurn, ConversationDelivery
from app.services import conversation_service as svc
from app.api.conversations import router


class APIClient:
    def __init__(self, app):
        self.app = app

    def request(self, method, url, **kwargs):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                return await client.request(method, url, **kwargs)
        return asyncio.run(run())

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)


@unittest.skipUnless(os.getenv("CONVERSATION_TEST_DATABASE_URL"), "requires disposable Postgres")
class ConversationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ["CONVERSATION_TEST_DATABASE_URL"])
        cls.Session = sessionmaker(bind=cls.engine)
        UserRole.__table__.create(cls.engine, checkfirst=True)
        User.__table__.create(cls.engine, checkfirst=True)
        path = Path(__file__).parents[1] / "alembic/versions/c8a12e40d931_add_slack_conversations.py"
        spec = importlib.util.spec_from_file_location("conversation_migration", path)
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)
        with cls.engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                cls.migration.upgrade()

    @classmethod
    def tearDownClass(cls):
        with cls.engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                cls.migration.downgrade()
        User.__table__.drop(cls.engine)
        UserRole.__table__.drop(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        self.user_id = uuid.uuid4()
        self.db = self.Session()
        self.db.add(User(id=self.user_id, email="operator@example.test", first_name="Test",
                         last_name="Operator", firebase_id="test-operator"))
        self.db.commit()
        self.saved = {k: getattr(settings, k) for k in ("SLACK_CONVERSATIONS_ENABLED", "SLACK_WORKSPACE_ID",
            "SLACK_APPLICATION_ID", "SLACK_USER_ID", "SLACK_BRAINS_USER_ID", "RUNNER_TOKEN")}
        for k, v in dict(SLACK_CONVERSATIONS_ENABLED=True, SLACK_WORKSPACE_ID="T1", SLACK_APPLICATION_ID="A1",
            SLACK_USER_ID="U1", SLACK_BRAINS_USER_ID=str(self.user_id), RUNNER_TOKEN="test-runner").items():
            setattr(settings, k, v)

    def tearDown(self):
        self.db.rollback()
        for model in (ConversationDelivery, ConversationTurn, Conversation, User):
            self.db.query(model).delete()
        self.db.commit()
        self.db.close()
        for k, v in self.saved.items():
            setattr(settings, k, v)

    def event(self, ts="1.0", root=None, text="Crie um arquivo de exemplo"):
        event = {"type": "message", "channel_type": "im", "channel": "D1", "user": "U1", "ts": ts, "text": text}
        if root:
            event["thread_ts"] = root
        return {"team_id": "T1", "api_app_id": "A1", "event_id": "Ev" + ts, "event": event}

    def test_root_is_new_chat_and_thread_is_resume(self):
        svc.receive(self.db, self.event())
        first = svc.claim(self.db, "worker", "host", "/repo")
        svc.update(self.db, first["id"], {"claim_token": first["claim_token"], "status": "waiting_input",
            "response": "Qual nome?", "session_id": "session-one"})
        svc.receive(self.db, self.event("2.0", "1.0", "exemplo.txt"))
        second = svc.claim(self.db, "worker", "host", "/repo")
        self.assertEqual(second["session_id"], "session-one")
        self.assertEqual(second["history"][0]["response"], "Qual nome?")
        svc.receive(self.db, self.event("3.0", text="Qual nome eu escolhi?"))
        third = svc.claim(self.db, "worker2", "host", "/repo")
        self.assertNotEqual(third["conversation_id"], first["conversation_id"])
        self.assertIsNone(third["session_id"])
        self.assertEqual(third["history"], [])

    def test_event_and_message_deduplication(self):
        event = self.event()
        svc.receive(self.db, event)
        svc.receive(self.db, event)
        event["event_id"] = "retry-with-new-envelope"
        svc.receive(self.db, event)
        self.assertEqual(self.db.query(ConversationTurn).count(), 1)
        self.assertEqual(self.db.query(ConversationDelivery).count(), 1)

    def test_concurrent_ingress_and_claim(self):
        barrier = threading.Barrier(2)
        errors = []
        def intake():
            with self.Session() as db:
                try:
                    barrier.wait()
                    svc.receive(db, self.event())
                except Exception as exc:
                    errors.append(exc)
        threads = [threading.Thread(target=intake) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(5)
        self.assertEqual(errors, [])
        self.assertEqual(self.db.query(ConversationTurn).count(), 1)
        claims = []
        def take():
            with self.Session() as db:
                barrier.wait()
                claims.append(svc.claim(db, "worker", "host", "/repo"))
        threads = [threading.Thread(target=take) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(5)
        self.assertEqual(sum(c is not None for c in claims), 1)

    def test_same_thread_waits_and_wrong_host_cannot_resume(self):
        svc.receive(self.db, self.event())
        first = svc.claim(self.db, "worker", "host", "/repo")
        svc.receive(self.db, self.event("2.0", "1.0"))
        self.assertIsNone(svc.claim(self.db, "other", "host", "/repo"))
        svc.update(self.db, first["id"], {"claim_token": first["claim_token"], "status": "succeeded", "response": "Pronto"})
        self.assertIsNone(svc.claim(self.db, "other", "other-host", "/repo"))
        self.assertIsNone(svc.claim(self.db, "other", "host", "/other-repo"))

    def test_expiry_fences_worker_and_does_not_replay(self):
        svc.receive(self.db, self.event())
        first = svc.claim(self.db, "worker", "host", "/repo")
        row = self.db.get(ConversationTurn, first["id"])
        row.lease_until = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()
        svc.expire_turns(self.db)
        self.assertIsNone(svc.claim(self.db, "worker", "host", "/repo"))
        with self.assertRaises(HTTPException):
            svc.update(self.db, first["id"], {"claim_token": first["claim_token"], "status": "succeeded"})

    def test_cancellation_and_terminal_retry(self):
        svc.receive(self.db, self.event())
        first = svc.claim(self.db, "worker", "host", "/repo")
        svc.receive(self.db, self.event("2.0", "1.0", "cancelar"))
        state = svc.update(self.db, first["id"], {"claim_token": first["claim_token"]})
        self.assertTrue(state["cancel_requested"])
        data = {"claim_token": first["claim_token"], "status": "cancelled"}
        svc.update(self.db, first["id"], data)
        count = self.db.query(ConversationDelivery).count()
        svc.update(self.db, first["id"], data)
        self.assertEqual(count, self.db.query(ConversationDelivery).count())

    def test_identity_required_and_unauthorized_ignored(self):
        event = self.event()
        event["event"]["user"] = "stranger"
        svc.receive(self.db, event)
        self.assertEqual(self.db.query(ConversationTurn).count(), 0)
        settings.SLACK_USER_ID = ""
        with self.assertRaises(RuntimeError):
            svc.receive(self.db, self.event())

    def test_file_only_message_is_a_turn(self):
        event = self.event(text="")
        event["event"].update(subtype="file_share", files=[{"id": "F1", "name": "frame.png"}])
        svc.receive(self.db, event)
        turn = svc.claim(self.db, "worker", "host", "/repo")
        self.assertEqual(turn["files"][0]["id"], "F1")

    def test_runner_endpoint_auth_and_artifact_checksum(self):
        app = FastAPI()
        app.include_router(router)
        def db_override():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = db_override
        client = APIClient(app)
        payload = {"runner_id": "worker", "host_id": "host", "cwd": "/repo"}
        self.assertEqual(client.post("/conversations/runner/claim", json=payload).status_code, 401)
        svc.receive(self.db, self.event())
        headers = {"X-Runner-Token": "test-runner"}
        turn = client.post("/conversations/runner/claim", json=payload, headers=headers).json()
        response = client.put(f"/conversations/runner/turns/{turn['id']}/artifacts/{'a' * 64}",
            params={"claim_token": turn["claim_token"], "name": "file.txt"}, content=b"wrong checksum", headers=headers)
        self.assertEqual(response.status_code, 422)
        content = b"artifact preview"
        checksum = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as tmp, patch.object(settings, "SLACK_ARTIFACT_DIR", tmp):
            for _ in range(2):
                response = client.put(f"/conversations/runner/turns/{turn['id']}/artifacts/{checksum}",
                    params={"claim_token": turn["claim_token"], "name": "preview.txt"}, content=content, headers=headers)
                self.assertEqual(response.status_code, 200)
            self.assertEqual(self.db.query(ConversationDelivery).filter_by(kind="file").count(), 1)
            self.assertEqual(len(list(Path(tmp).rglob("*preview.txt"))), 1)

    def test_ack_only_after_persistence(self):
        from app.slack.actions import _handle
        from unittest.mock import Mock
        client = Mock()
        request = Mock(type="events_api", payload=self.event(), envelope_id="envelope")
        with patch("app.slack.conversations.receive_event", side_effect=RuntimeError("database unavailable")):
            _handle(client, request)
        client.send_socket_mode_response.assert_not_called()
        with patch("app.slack.conversations.receive_event") as receive:
            _handle(client, request)
        receive.assert_called_once()
        client.send_socket_mode_response.assert_called_once()

    def test_unknown_delivery_outcome_is_not_retried(self):
        from app.slack.conversations import deliver_one
        from unittest.mock import Mock
        svc.receive(self.db, self.event())
        web = Mock()
        web.chat_postMessage.side_effect = TimeoutError()
        self.assertTrue(deliver_one(self.db, web))
        self.assertFalse(deliver_one(self.db, web))
        self.assertEqual(self.db.query(ConversationDelivery).one().status, "uncertain")


if __name__ == "__main__":
    unittest.main()
