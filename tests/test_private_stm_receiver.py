"""Synthetic-only private-receiver acceptance and negative boundary tests."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from private_stm_receiver import PrivateSTMReceiver, HISTORICAL_ONLY


NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
SCOPE = ("tenant-a", "owner-a", "agent-a")
OTHER = ("tenant-a", "owner-b", "agent-a")


@dataclass(frozen=True)
class SyntheticSTMRecord:
    schema: str = "STM_HISTORICAL_HANDOFF_CANDIDATE_V1"
    tenant_id: str = SCOPE[0]
    owner_id: str = SCOPE[1]
    agent_id: str = SCOPE[2]
    turn_id: str = "turn-1"
    conversation_id: str = "conversation-1"
    role: str = "user"
    content: str = "A deliberately synthetic private sentence."
    source_id: str = "host:synthetic:turn-1"
    privacy_scope: str = "private"
    event_time: str = "2026-09-20T12:00:00+00:00"
    recorded_at: str = "2026-09-20T12:01:00+00:00"
    supersedes_id: str | None = None
    expires_at: str = "2026-11-04T12:00:00+00:00"
    source_version_digest: str = ""
    result_semantics: str = HISTORICAL_ONLY


def stm_digest(record):
    # Independent oracle copied from the documented STM external contract,
    # not a call into the receiver's validation routine.
    data = {"scope": [record.tenant_id, record.owner_id, record.agent_id],
            "turn": [record.turn_id, record.conversation_id, record.role,
                     record.content, record.source_id, record.privacy_scope,
                     record.event_time, record.recorded_at,
                     record.supersedes_id, record.expires_at]}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")).encode("utf-8")).hexdigest()


def exact(record=None, **changes):
    record = replace(record or SyntheticSTMRecord(), **changes)
    return replace(record, source_version_digest=stm_digest(record))


class PrivateReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private"
        self.key = secrets.token_bytes(32)
        self.mac = secrets.token_bytes(32)
        self.consent = True
        self.authorized = True
        self.now = NOW
        self.principal = object()
        self.target = SimpleNamespace(
            destination_id="host-owned-private-dms",
            retention_until=NOW + timedelta(days=400),
            supports_deletion=True, supports_correction=True,
            supports_consent_revocation=True, private_destination=True,
            supports_scope_isolation=True,
        )

    def authorize(self, principal, action, scope, privacy, source_id, target):
        return (self.authorized and principal is self.principal and
                (scope == SCOPE or (action == "retention_expire" and scope == ("*", "*", "*"))))

    def consent_check(self, principal, action, scope, privacy, source_id, target):
        return self.consent and principal is self.principal and scope == SCOPE

    def receiver(self):
        return PrivateSTMReceiver(
            directory=self.path, destination_id="host-owned-private-dms",
            principal=self.principal, encryption_key=lambda: self.key,
            receipt_key=lambda: self.mac, authorize=self.authorize,
            consent=self.consent_check, clock=lambda: self.now,
        )

    def test_synthetic_durable_handoff_and_independent_reopen_readback(self):
        record = exact()
        key = "a" * 64
        first = self.receiver().submit(record, target=self.target, idempotency_key=key)
        with sqlite3.connect(self.path / "private_stm.sqlite3") as db:
            encrypted, nonce = db.execute("SELECT ciphertext, nonce FROM records").fetchone()
        self.assertNotIn(record.content.encode("utf-8"), encrypted)
        self.assertEqual(len(nonce), 12)
        # A newly constructed reader/connection survives process replacement.
        new_instance = self.receiver()
        self.assertTrue(new_instance.verify_receipt(first, record, key))
        second = new_instance.submit(record, target=self.target, idempotency_key=key)
        self.assertEqual(first, second)
        with sqlite3.connect(self.path / "private_stm.sqlite3") as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM records").fetchone()[0], 1)

    def test_content_limit_matches_stm_utf8_byte_bound(self):
        receiver = self.receiver()
        with self.assertRaisesRegex(ValueError, "maximum content bytes"):
            receiver.submit(exact(content="é" * 131073), target=self.target,
                            idempotency_key="f" * 64)
        with sqlite3.connect(self.path / "private_stm.sqlite3") as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM records").fetchone()[0], 0)

    def test_wrong_key_payload_digest_or_receipt_fails(self):
        receiver = self.receiver()
        row = exact()
        key = "b" * 64
        receipt = receiver.submit(row, target=self.target, idempotency_key=key)
        changed = exact(row, content="Different private sentence")
        with self.assertRaises(PermissionError):
            receiver.submit(changed, target=self.target, idempotency_key=key)
        self.assertFalse(receiver.verify_receipt(receipt, changed, key))
        self.assertFalse(receiver.verify_receipt({**receipt, "external_record_id": "dms:forged"}, row, key))
        self.assertFalse(receiver.verify_receipt({**receipt, "receipt_mac": "0" * 64}, row, key))
        with self.assertRaises(ValueError):
            receiver.submit(replace(row, content="tampered"), target=self.target,
                            idempotency_key="c" * 64)

    def test_consent_and_owner_scope_denials(self):
        receiver = self.receiver()
        row = exact()
        self.consent = False
        with self.assertRaises(PermissionError):
            receiver.submit(row, target=self.target, idempotency_key="c" * 64)
        self.consent = True
        other = exact(row, owner_id=OTHER[1])
        with self.assertRaises(PermissionError):
            receiver.submit(other, target=self.target, idempotency_key="d" * 64)
        self.authorized = False
        with self.assertRaises(PermissionError):
            receiver.submit(row, target=self.target, idempotency_key="e" * 64)

    def test_denies_wrong_or_nonprivate_target(self):
        receiver = self.receiver()
        row = exact()
        for changes in ({"private_destination": False},
                        {"destination_id": "public-github"},
                        {"supports_deletion": False},
                        {"retention_until": NOW - timedelta(seconds=1)}):
            with self.subTest(changes=changes):
                with self.assertRaises(PermissionError):
                    receiver.submit(row, target=SimpleNamespace(**{**vars(self.target), **changes}),
                                    idempotency_key="f" * 64)

    def test_target_erase_is_idempotent_and_prevents_reingestion(self):
        receiver = self.receiver()
        row = exact()
        key = "1" * 64
        receipt = receiver.submit(row, target=self.target, idempotency_key=key)
        self.assertEqual(receiver.erase_source(scope=SCOPE, source_id=row.source_id), 1)
        self.assertEqual(receiver.erase_source(scope=SCOPE, source_id=row.source_id), 0)
        self.assertFalse(receiver.verify_receipt(receipt, row, key))
        with self.assertRaises(PermissionError):
            receiver.submit(row, target=self.target, idempotency_key=key)
        with sqlite3.connect(self.path / "private_stm.sqlite3") as db:
            self.assertEqual(db.execute("SELECT ciphertext, nonce FROM records").fetchone(),
                             (None, None))

    def test_scope_withdrawal_wipes_all_active_content_and_survives_restart(self):
        receiver = self.receiver()
        first = exact()
        second = exact(turn_id="turn-2", source_id="host:synthetic:turn-2")
        receiver.submit(first, target=self.target, idempotency_key="2" * 64)
        receiver.submit(second, target=self.target, idempotency_key="3" * 64)
        self.assertEqual(receiver.revoke_scope(scope=SCOPE), 2)
        with self.assertRaises(PermissionError):
            self.receiver().submit(first, target=self.target, idempotency_key="2" * 64)
        with sqlite3.connect(self.path / "private_stm.sqlite3") as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM records WHERE ciphertext IS NOT NULL").fetchone()[0], 0)

    def test_fresh_consent_withdrawal_blocks_read_and_retry_then_allows_revocation(self):
        receiver = self.receiver()
        row = exact()
        key = "8" * 64
        receipt = receiver.submit(row, target=self.target, idempotency_key=key)
        self.consent = False
        with self.assertRaises(PermissionError):
            receiver.verify_receipt(receipt, row, key)
        with self.assertRaises(PermissionError):
            receiver.submit(row, target=self.target, idempotency_key=key)
        # Withdrawal must remain operable even when consent has disappeared.
        self.assertEqual(receiver.revoke_scope(scope=SCOPE), 1)
        self.consent = True
        with self.assertRaises(PermissionError):
            receiver.submit(row, target=self.target, idempotency_key=key)

    def test_expired_stm_source_cannot_enter_vault(self):
        receiver = self.receiver()
        with self.assertRaises(PermissionError):
            receiver.submit(exact(expires_at=NOW.isoformat()),
                            target=self.target, idempotency_key="9" * 64)
        with self.assertRaises(PermissionError):
            receiver.submit(exact(expires_at=None), target=self.target,
                            idempotency_key="a" * 64)

    def test_correction_supersedes_without_losing_source_provenance(self):
        receiver = self.receiver()
        first = exact()
        old_receipt = receiver.submit(first, target=self.target, idempotency_key="4" * 64)
        correction = exact(turn_id="turn-2", source_id="host:synthetic:turn-2",
                           supersedes_id="turn-1", content="Corrected synthetic sentence")
        corrected = receiver.submit(correction, target=self.target, idempotency_key="5" * 64)
        self.assertFalse(receiver.verify_receipt(old_receipt, first, "4" * 64))
        self.assertTrue(receiver.verify_receipt(corrected, correction, "5" * 64))
        with sqlite3.connect(self.path / "private_stm.sqlite3") as db:
            self.assertEqual(db.execute("SELECT superseded_by FROM records WHERE idempotency_key=?",
                                        ("4" * 64,)).fetchone()[0], corrected["external_record_id"])

    def test_retention_removes_expired_content_without_extending_deadline(self):
        receiver = self.receiver()
        row = exact()
        receipt = receiver.submit(row, target=self.target, idempotency_key="6" * 64)
        self.now = self.target.retention_until
        self.assertFalse(receiver.verify_receipt(receipt, row, "6" * 64))
        self.assertEqual(receiver.expire_due(), 1)
        self.assertEqual(receiver.expire_due(), 0)
        with sqlite3.connect(self.path / "private_stm.sqlite3") as db:
            self.assertIsNone(db.execute("SELECT ciphertext FROM records").fetchone()[0])

    def test_public_git_root_is_not_a_private_vault(self):
        checkout = Path(__file__).resolve().parents[1]
        with self.assertRaises(PermissionError):
            PrivateSTMReceiver(
                directory=checkout / "hypothetical-vault", destination_id="private",
                principal=self.principal, encryption_key=lambda: self.key,
                receipt_key=lambda: self.mac, authorize=self.authorize,
                consent=self.consent_check,
            )

    def test_key_rotation_without_migration_fails_closed(self):
        receiver = self.receiver()
        receiver.submit(exact(), target=self.target, idempotency_key="7" * 64)
        old_mac = self.mac
        self.mac = secrets.token_bytes(32)
        with self.assertRaises(PermissionError):
            self.receiver()
        self.mac = old_mac
        self.key = secrets.token_bytes(32)
        with self.assertRaises(PermissionError):
            self.receiver()


if __name__ == "__main__":
    unittest.main()
