"""Disposable synthetic host-policy integration tests, never personal data."""

import asyncio
from contextvars import copy_context
from datetime import timedelta
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from private_stm_policy_host import HostPolicyBoundary
from test_private_stm_receiver import exact, NOW, SCOPE, OTHER, synthetic_windows_acl


class AtomicHostPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private"
        self.principal = object()
        self.allowed = True
        self.grant_evidence = True
        self.key = secrets.token_bytes(32)
        self.receipt_key = secrets.token_bytes(32)
        self.scope_key = secrets.token_bytes(32)
        self.target = SimpleNamespace(
            destination_id="synthetic-private-receiver",
            retention_until=NOW + timedelta(days=400),
            supports_deletion=True, supports_correction=True,
            supports_consent_revocation=True, private_destination=True,
            supports_scope_isolation=True,
        )
        self.boundary = HostPolicyBoundary(
            directory=self.path, principal=self.principal, scope=SCOPE,
            authenticate=lambda p, s: self.allowed and p is self.principal and s == SCOPE,
            verify_consent_grant=lambda p, s: self.grant_evidence and p is self.principal and s == SCOPE,
            scope_key=lambda: self.scope_key,
            verify_windows_acl=synthetic_windows_acl,
        )
        self.receiver = self.boundary.bind_receiver(
            destination_id="synthetic-private-receiver",
            encryption_key=lambda: self.key,
            receipt_key=lambda: self.receipt_key,
            clock=lambda: NOW,
        )

    def _write(self, token="a"):
        return self.receiver.submit(exact(), target=self.target,
                                    idempotency_key=token * 64)

    def test_no_consent_or_fabricated_identity_cannot_write(self):
        with self.assertRaises(PermissionError):
            self._write()
        self.grant_evidence = False
        with self.assertRaises(PermissionError):
            self.boundary.grant_once()
        self.grant_evidence = True
        self.boundary.grant_once()
        self.allowed = False
        with self.assertRaises(PermissionError):
            self._write()
        self.allowed = True
        with self.assertRaises(PermissionError):
            with self.boundary.lease(object(), "long_term_export", SCOPE, None, None, None):
                pass
        with self.assertRaises(PermissionError):
            with self.boundary.lease(self.principal, "long_term_export", OTHER, None, None, None):
                pass
        with self.assertRaises(PermissionError):
            self.receiver.expire_due()

    def test_scope_key_change_cannot_create_fresh_grant_after_withdrawal(self):
        self.boundary.grant_once()
        self.boundary.withdraw_and_revoke()
        with self.assertRaises(PermissionError):
            HostPolicyBoundary(directory=self.path, principal=self.principal,
                scope=SCOPE, authenticate=lambda p, s: True,
                verify_consent_grant=lambda p, s: True,
                scope_key=lambda: secrets.token_bytes(32),
                verify_windows_acl=synthetic_windows_acl)
        reopened = HostPolicyBoundary(directory=self.path, principal=self.principal,
            scope=SCOPE, authenticate=lambda p, s: p is self.principal,
            verify_consent_grant=lambda p, s: True,
            scope_key=lambda: self.scope_key,
            verify_windows_acl=synthetic_windows_acl)
        with self.assertRaises(PermissionError):
            reopened.grant_once()

    def test_factory_fixes_lease_and_withdrawal_blocks_retry(self):
        self.assertIs(self.receiver._policy_lease.__self__, self.boundary)
        with self.assertRaises(RuntimeError):
            self.boundary.bind_receiver(destination_id="another", encryption_key=lambda: self.key,
                                        receipt_key=lambda: self.receipt_key, clock=lambda: NOW)
        self.boundary.grant_once()
        receipt = self._write()
        self.assertTrue(self.receiver.verify_receipt(receipt, exact(), "a" * 64))
        self.assertEqual(self.boundary.withdraw_and_revoke(), 1)
        with self.assertRaises(PermissionError):
            self.receiver.verify_receipt(receipt, exact(), "a" * 64)
        with self.assertRaises(PermissionError):
            self._write("b")
        with self.assertRaises(PermissionError):
            self.boundary.grant_once()
        with sqlite3.connect(self.receiver.database) as db:
            self.assertIsNone(db.execute("SELECT ciphertext FROM records").fetchone()[0])

    def test_revoke_failure_persists_fail_closed_pending_state_until_retry(self):
        self.boundary.grant_once()
        self._write()
        original = self.receiver.revoke_scope
        self.receiver.revoke_scope = lambda *, scope: (_ for _ in ()).throw(RuntimeError("DMS failure"))
        with self.assertRaisesRegex(RuntimeError, "DMS failure"):
            self.boundary.withdraw_and_revoke()
        self.receiver.revoke_scope = original
        self.assertFalse(self.boundary.consent(self.principal, "long_term_export", SCOPE,
                                               "private", "synthetic", self.target))
        with self.boundary.lease(self.principal, "long_term_export", SCOPE,
                                 "private", "synthetic", self.target):
            self.assertFalse(self.boundary.consent(self.principal, "long_term_export", SCOPE,
                                                   "private", "synthetic", self.target))
        with self.assertRaises(PermissionError):
            self._write("c")
        # Ciphertext remains pending erasure but cannot be read or re-ingested.
        with sqlite3.connect(self.receiver.database) as db:
            self.assertIsNotNone(db.execute("SELECT ciphertext FROM records").fetchone()[0])
        # Simulate a fresh service instance after the crashed erasure step.
        recovered = HostPolicyBoundary(directory=self.path, principal=self.principal,
            scope=SCOPE, authenticate=lambda p, s: p is self.principal,
            verify_consent_grant=lambda p, s: False,
            scope_key=lambda: self.scope_key,
            verify_windows_acl=synthetic_windows_acl)
        recovered_receiver = recovered.bind_receiver(destination_id="synthetic-private-receiver",
            encryption_key=lambda: self.key, receipt_key=lambda: self.receipt_key,
            clock=lambda: NOW)
        with self.assertRaises(PermissionError):
            recovered_receiver.submit(exact(), target=self.target, idempotency_key="d" * 64)
        self.assertEqual(recovered.withdraw_and_revoke(), 1)
        with sqlite3.connect(self.receiver.database) as db:
            self.assertIsNone(db.execute("SELECT ciphertext FROM records").fetchone()[0])

    def test_threaded_withdrawal_waits_for_consent_locked_write(self):
        self.boundary.grant_once()
        entered = threading.Event()
        release = threading.Event()
        withdraw_started = threading.Event()
        withdrawn = threading.Event()
        errors = []
        original = self.boundary._authenticate

        def paused_auth(p, s):
            if threading.current_thread().name == "private-writer" and not entered.is_set():
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("synthetic test timeout")
            return original(p, s)

        self.boundary._authenticate = paused_auth

        def write():
            try:
                self._write()
            except BaseException as exc:
                errors.append(exc)

        def withdraw():
            withdraw_started.set()
            try:
                self.boundary.withdraw_and_revoke()
                withdrawn.set()
            except BaseException as exc:
                errors.append(exc)

        writer = threading.Thread(target=write, name="private-writer")
        writer.start()
        self.assertTrue(entered.wait(5))
        revoker = threading.Thread(target=withdraw)
        revoker.start()
        self.assertTrue(withdraw_started.wait(5))
        self.assertFalse(withdrawn.wait(0.15))
        release.set()
        writer.join(5)
        revoker.join(5)
        self.assertEqual(errors, [])
        self.assertFalse(writer.is_alive() or revoker.is_alive())
        self.assertTrue(withdrawn.is_set())
        with sqlite3.connect(self.receiver.database) as db:
            self.assertIsNone(db.execute("SELECT ciphertext FROM records").fetchone()[0])

    def test_copied_context_cannot_reuse_other_threads_transaction(self):
        result = []
        with self.boundary.lease(self.principal, "long_term_revoke", SCOPE, None, None, None):
            context = copy_context()
            def try_reuse():
                try:
                    context.run(lambda: self.boundary.authorize(self.principal,
                        "long_term_revoke", SCOPE, None, None, None))
                    context.run(lambda: self.boundary.lease(self.principal,
                        "long_term_revoke", SCOPE, None, None, None).__enter__())
                except PermissionError:
                    result.append("denied")
            child = threading.Thread(target=try_reuse)
            child.start()
            child.join(5)
            self.assertFalse(child.is_alive())
        self.assertEqual(result, ["denied"])

    def test_async_child_task_cannot_inherit_parent_policy_lease(self):
        async def parent():
            with self.boundary.lease(self.principal, "long_term_revoke", SCOPE,
                                     None, None, None):
                async def child():
                    allowed = self.boundary.authorize(self.principal,
                        "long_term_revoke", SCOPE, None, None, None)
                    try:
                        with self.boundary.lease(self.principal,
                                "long_term_revoke", SCOPE, None, None, None):
                            pass
                    except PermissionError:
                        return allowed, "denied"
                    return allowed, "bypassed"
                return await asyncio.create_task(child())
        self.assertEqual(asyncio.run(parent()), (False, "denied"))

    def test_separate_python_process_cannot_bypass_sqlite_write_lease(self):
        # A second interpreter with an independently opened SQLite connection
        # is blocked by the host's BEGIN IMMEDIATE until the first lease exits.
        code = (
            "import sys;sys.path.insert(0,sys.argv[2]);"
            "from private_stm_policy_host import HostPolicyBoundary;"
            "p='trusted';b=HostPolicyBoundary(directory=sys.argv[1],scope=('tenant-a','owner-a','agent-a'),"
            "principal=p,authenticate=lambda principal,scope:principal==p,"
            "verify_consent_grant=lambda principal,scope:False,"
            "scope_key=lambda:bytes.fromhex(sys.argv[3]),"
            "verify_windows_acl=lambda path:True);"
            "print('ready',flush=True);"
            "cm=b.lease(p,'long_term_revoke',b.scope,None,None,None);"
            "print('attempting',flush=True);"
            "cm.__enter__();print('acquired',flush=True);cm.__exit__(None,None,None)"
        )
        # Start child before parent lease so initialization is out of the way.
        # The child waits for the parent to confirm lock ownership using a
        # small stdin handshake performed in the child code below.
        code = code.replace("cm=b.lease", "sys.stdin.readline();cm=b.lease")
        child = subprocess.Popen([sys.executable, "-c", code, str(self.path),
                                  str(Path(__file__).resolve().parents[1] / "tools"),
                                  self.scope_key.hex()],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "ready")
            with self.boundary.lease(self.principal, "long_term_revoke", SCOPE, None, None, None):
                child.stdin.write("go\n")
                child.stdin.flush()
                self.assertEqual(child.stdout.readline().strip(), "attempting")
                time.sleep(0.15)
                self.assertIsNone(child.poll())
            stdout, stderr = child.communicate(timeout=8)
            self.assertEqual(child.returncode, 0, stderr)
            self.assertIn("acquired", stdout)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=3)


if __name__ == "__main__":
    unittest.main()
