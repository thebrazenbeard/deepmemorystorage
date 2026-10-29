"""Host-owned, cross-process consent serialization for the private STM sink.

Source-stage adapter only. A qualified host must attest the caller on each
operation and protect this directory/keys. Nothing here authenticates a human
from a Windows account SID or enables private history collection.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Callable

from private_stm_receiver import PrivateSTMReceiver, _private_directory


_CURRENT = ContextVar("private_stm_host_policy_transaction", default=None)
_OPERATIONS = frozenset({"long_term_export", "long_term_read",
                         "long_term_delete", "long_term_revoke",
                         "retention_expire"})


def _task():
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None


class HostPolicyBoundary:
    """Bind one trusted authenticated host principal to one exact STM scope.

    The SQLite BEGIN IMMEDIATE lease serializes across cooperating host
    processes, not merely Python threads. All private receiver operations and
    consent withdrawal must enter via this adapter in the qualified host.
    ``authenticate`` is a REQUIRED host-provided fresh authentication probe;
    the adapter cannot manufacture proof of the host's identity boundary.
    """

    def __init__(self, *, directory: str | Path, scope: tuple[str, str, str],
                 principal: object, authenticate: Callable[[object, tuple], bool],
                 verify_consent_grant: Callable[[object, tuple], bool],
                 scope_key: Callable[[], bytes],
                 authorize_maintenance: Callable[[object], bool] | None = None,
                 verify_windows_acl: Callable[[Path], bool] | None = None):
        if (len(scope) != 3 or any(not isinstance(s, str) or not s.strip()
                                  for s in scope)):
            raise ValueError("exact tenant/owner/agent scope required")
        if (principal is None or not callable(authenticate)
                or not callable(verify_consent_grant) or not callable(scope_key)):
            raise TypeError("host principal, authentication, consent and key callbacks required")
        self.directory = _private_directory(directory)
        if os.name == "nt" and (not callable(verify_windows_acl)
                                or verify_windows_acl(self.directory) is not True):
            raise PermissionError("host policy directory ACL is not qualified")
        self._verify_windows_acl = verify_windows_acl
        self.scope = tuple(scope)
        self.principal = principal
        self._authenticate = authenticate
        self._verify_consent_grant = verify_consent_grant
        self._authorize_maintenance = authorize_maintenance
        key = scope_key()
        if not isinstance(key, bytes) or len(key) != 32:
            raise PermissionError("host-owned private scope key is invalid")
        self._scope_tag = hmac.new(key, json.dumps(self.scope,
            separators=(",", ":")).encode("utf-8"), hashlib.sha256).hexdigest()
        self.database = self.directory / "host_policy.sqlite3"
        self._receiver = None
        if self.database.is_symlink():
            raise PermissionError("host policy database link forbidden")
        if not self.database.exists():
            fd = os.open(self.database, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        if os.name == "posix" and self.database.stat().st_mode & 0o077:
            raise PermissionError("host policy database is not owner-only")
        with sqlite3.connect(self.database, timeout=20) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE IF NOT EXISTS scopes (tag TEXT PRIMARY KEY, state TEXT NOT NULL CHECK (state IN ('active','withdraw_pending','withdrawn')))")
            db.execute("CREATE TABLE IF NOT EXISTS key_binding (purpose TEXT PRIMARY KEY, commitment TEXT NOT NULL)")
            commitment = hmac.new(key, b"private-stm-host-policy-v1:key-binding", hashlib.sha256).hexdigest()
            saved = db.execute("SELECT commitment FROM key_binding WHERE purpose='scope'").fetchone()
            if saved and not hmac.compare_digest(saved[0], commitment):
                raise PermissionError("host policy scope key changed without authorized migration")
            if not saved:
                db.execute("INSERT INTO key_binding VALUES ('scope', ?)", (commitment,))

    def _auth(self, principal, action, scope):
        if (action == "retention_expire" and scope == ("*", "*", "*")
                and principal is self.principal
                and callable(self._authorize_maintenance)
                and self._authorize_maintenance(principal) is True):
            return
        if (principal is not self.principal or scope != self.scope
                or self._authenticate(principal, scope) is not True):
            raise PermissionError("current trusted host identity denied")
        if action not in _OPERATIONS and action != "consent_grant":
            raise PermissionError("unsupported private host operation")

    @contextmanager
    def lease(self, principal, action, scope, privacy, source_id, target):
        """Host-controlled lock acquired before auth and held past DMS COMMIT."""
        existing = _CURRENT.get()
        if existing is not None:
            if (existing[0] is not self or existing[2] != os.getpid()
                    or existing[3] != threading.get_ident()
                    or existing[4] is not _task()):
                raise PermissionError("nested foreign or copied-context policy lease")
            self._auth(principal, action, scope)
            yield
            return
        db = sqlite3.connect(self.database, timeout=20, isolation_level=None)
        db.execute("PRAGMA busy_timeout=20000")
        token = None
        try:
            db.execute("BEGIN IMMEDIATE")
            self._auth(principal, action, scope)
            token = _CURRENT.set((self, db, os.getpid(), threading.get_ident(), _task()))
            yield
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            if token is not None:
                _CURRENT.reset(token)
            db.close()

    def _active_db(self):
        state = _CURRENT.get()
        if (state is None or state[0] is not self
                or state[2] != os.getpid() or state[3] != threading.get_ident()
                or state[4] is not _task()):
            raise PermissionError("operation requires active host policy lease")
        return state[1]

    def authorize(self, principal, action, scope, privacy, source_id, target):
        try:
            self._active_db()
            self._auth(principal, action, scope)
        except (PermissionError, TypeError):
            return False
        return True

    def consent(self, principal, action, scope, privacy, source_id, target):
        if self.authorize(principal, action, scope, privacy, source_id, target) is not True:
            return False
        row = self._active_db().execute(
            "SELECT state FROM scopes WHERE tag=?", (self._scope_tag,)).fetchone()
        return row is not None and row[0] == "active"

    def grant_once(self):
        """Host-authorized explicit initial consent; never undo withdrawal."""
        with self.lease(self.principal, "consent_grant", self.scope, None, None, None):
            if self._verify_consent_grant(self.principal, self.scope) is not True:
                raise PermissionError("fresh separate long-term consent proof denied")
            db = self._active_db()
            if db.execute("SELECT 1 FROM scopes WHERE tag=?", (self._scope_tag,)).fetchone():
                raise PermissionError("existing consent state cannot be reset")
            db.execute("INSERT INTO scopes VALUES (?, 'active')", (self._scope_tag,))

    def bind_receiver(self, *, destination_id, encryption_key, receipt_key, clock):
        """Factory prevents untrusted callers from substituting a no-op lease."""
        if self._receiver is not None:
            raise RuntimeError("only one receiver binding per host policy instance")
        self._receiver = PrivateSTMReceiver(
            directory=self.directory, destination_id=destination_id,
            principal=self.principal, encryption_key=encryption_key,
            receipt_key=receipt_key, authorize=self.authorize,
            consent=self.consent, policy_lease=self.lease, clock=clock,
            verify_windows_acl=self._verify_windows_acl,
        )
        return self._receiver

    def withdraw_and_revoke(self):
        """Persist denial *first*, then tombstone; retry incomplete erasure.

        Separate policy and DMS SQLite databases cannot commit atomically.
        Committing ``withdraw_pending`` under the same host lease before the
        DMS erasure guarantees no new reads/writes after an acknowledged
        withdrawal intent, even if erasure crashes or raises. On retry the
        pending tombstone is idempotently completed before returning success.
        """
        with self.lease(self.principal, "long_term_revoke", self.scope, None, None, None):
            db = self._active_db()
            row = db.execute("SELECT state FROM scopes WHERE tag=?", (self._scope_tag,)).fetchone()
            if row is None:
                raise PermissionError("scope has no prior consent")
            db.execute("UPDATE scopes SET state='withdraw_pending' WHERE tag=?", (self._scope_tag,))
        if self._receiver is None:
            raise RuntimeError("withdrawal persisted; receiver erasure requires retry")
        erased = self._receiver.revoke_scope(scope=self.scope)
        with self.lease(self.principal, "long_term_revoke", self.scope, None, None, None):
            self._active_db().execute("UPDATE scopes SET state='withdrawn' WHERE tag=?",
                                      (self._scope_tag,))
        return erased


__all__ = ["HostPolicyBoundary"]
