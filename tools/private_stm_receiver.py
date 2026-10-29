"""Source-stage, local-only private STM handoff sink.

This is *not* a network endpoint or a provisioned Vera service. An embedding
host must supply authenticated principal, current authorization/consent,
protected keys, a durable clock and an independently qualified backup policy.
No public ledger or Git file is written by this module.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
from typing import Callable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


HISTORICAL_ONLY = "HISTORICAL_EVIDENCE_ONLY_NOT_CURRENT_MEMORY_OR_AUTHORITY"
SCHEMA = "STM_HISTORICAL_HANDOFF_CANDIDATE_V1"
HEX_64 = re.compile(r"[a-f0-9]{64}\Z")
MAX_CONTENT_BYTES = 262_144  # Match STM's archive content bound.
REQUIRED = frozenset({
    "schema", "tenant_id", "owner_id", "agent_id", "turn_id",
    "conversation_id", "role", "content", "source_id", "privacy_scope",
    "event_time", "recorded_at", "supersedes_id", "expires_at",
    "source_version_digest", "result_semantics",
})


def _canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True).encode("utf-8")


def _time(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


def _scope(row: dict) -> tuple[str, str, str]:
    values = (row["tenant_id"], row["owner_id"], row["agent_id"])
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("complete tenant/owner/agent scope required")
    return values


def _record_dict(record: object) -> dict:
    if is_dataclass(record) and not isinstance(record, type):
        row = asdict(record)
    else:
        row = {key: getattr(record, key, None) for key in REQUIRED}
    if set(row) != REQUIRED or row["schema"] != SCHEMA or row["result_semantics"] != HISTORICAL_ONLY:
        raise ValueError("exact historical-only STM handoff schema required")
    _scope(row)
    for key in ("turn_id", "conversation_id", "role", "content", "source_id", "privacy_scope"):
        if not isinstance(row[key], str) or not row[key].strip():
            raise ValueError(f"invalid {key}")
    if len(row["content"].encode("utf-8")) > MAX_CONTENT_BYTES:
        raise ValueError("historical handoff exceeds maximum content bytes")
    if row["supersedes_id"] is not None and (
        not isinstance(row["supersedes_id"], str) or not row["supersedes_id"].strip()
    ):
        raise ValueError("invalid supersedes_id")
    _time(row["event_time"])
    _time(row["recorded_at"])
    if row["expires_at"] is not None:
        _time(row["expires_at"])
    digest = row["source_version_digest"]
    if not isinstance(digest, str) or HEX_64.fullmatch(digest) is None:
        raise ValueError("invalid source version digest")
    # Recompute the digest from STM's published handoff contract, not a claim
    # supplied by the caller. This binds exact content and provenance.
    source = {
        "scope": list(_scope(row)),
        "turn": [row[key] for key in ("turn_id", "conversation_id", "role",
                                     "content", "source_id", "privacy_scope",
                                     "event_time", "recorded_at", "supersedes_id",
                                     "expires_at")],
    }
    if not hmac.compare_digest(hashlib.sha256(_canonical(source)).hexdigest(), digest):
        raise ValueError("source version digest does not match exact STM content")
    return row


def _private_directory(path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    # A public Git checkout, including a parent checkout, is never a vault.
    # Some sandbox mounts contain inert empty .git placeholders; only a real
    # worktree marker (HEAD or a gitdir link-file) identifies a checkout.
    def is_checkout(parent: Path) -> bool:
        marker = parent / ".git"
        return ((marker.is_dir() and (marker / "HEAD").is_file())
                or (marker.is_file() and marker.read_text(errors="replace").startswith("gitdir:")))

    if any(is_checkout(parent) for parent in (target, *target.parents)):
        raise PermissionError("private storage must be outside all Git worktrees")
    if target.exists() and not target.is_dir():
        raise ValueError("private storage path is not a directory")
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        info = target.stat()
        if (info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise PermissionError("private storage directory is not owner-only")
    # On Windows, effective ACL checks must be performed by host qualification;
    # source tests here cannot certify a specific Windows service token/ACL.
    return target


class PrivateSTMReceiver:
    """An authenticated-host-injected STM HistoricalSink, not an HTTP server.

    ``authorize`` and ``consent`` must read live, authoritative state and return
    literal True. The host must serialize consent withdrawal against writes;
    this module cannot turn user-provided callback claims into verified identity.
    Both keys are host-owned 32-byte secrets, never stored in the database.
    """

    def __init__(self, *, directory: str | Path, destination_id: str,
                 principal: object, encryption_key: Callable[[], bytes],
                 receipt_key: Callable[[], bytes], authorize: Callable,
                 consent: Callable, clock: Callable[[], datetime] =
                 lambda: datetime.now(timezone.utc),
                 verify_windows_acl: Callable[[Path], bool] | None = None) -> None:
        if not isinstance(destination_id, str) or not destination_id.strip():
            raise ValueError("destination_id required")
        if principal is None or not all(callable(x) for x in
              (encryption_key, receipt_key, authorize, consent, clock)):
            raise TypeError("authenticated host principal and live host callbacks required")
        self.directory = _private_directory(directory)
        if os.name == "nt":
            if not callable(verify_windows_acl) or verify_windows_acl(self.directory) is not True:
                raise PermissionError("Windows vault owner/service ACL is unverified")
        self.database = self.directory / "private_stm.sqlite3"
        self.destination_id = destination_id
        self.principal = principal
        self._encryption_key = encryption_key
        self._receipt_key = receipt_key
        self._authorize = authorize
        self._consent = consent
        self._clock = clock
        existed = self.database.exists()
        self._initialized = False
        if not existed:
            try:
                fd = os.open(self.database, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
        if os.name == "posix" and stat.S_IMODE(self.database.stat().st_mode) & 0o077:
            raise PermissionError("private database permissions are not owner-only")
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                  idempotency_key TEXT PRIMARY KEY, external_record_id TEXT UNIQUE NOT NULL,
                  scope_token TEXT NOT NULL, source_token TEXT NOT NULL,
                  turn_token TEXT NOT NULL, privacy_token TEXT NOT NULL,
                  source_version_digest TEXT NOT NULL, nonce BLOB,
                  ciphertext BLOB, retention_until TEXT NOT NULL,
                  superseded_by TEXT, erased_at TEXT);
                CREATE INDEX IF NOT EXISTS records_source ON records(scope_token, source_token);
                CREATE INDEX IF NOT EXISTS records_turn ON records(scope_token, turn_token);
                CREATE TABLE IF NOT EXISTS tombstones (
                  scope_token TEXT NOT NULL, source_token TEXT NOT NULL,
                  erased_at TEXT NOT NULL, PRIMARY KEY(scope_token, source_token));
                CREATE TABLE IF NOT EXISTS revoked_scopes (
                  scope_token TEXT PRIMARY KEY, erased_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS key_binding (
                  purpose TEXT PRIMARY KEY, commitment TEXT NOT NULL);
            """)
            if existed and db.execute("SELECT COUNT(*) FROM key_binding").fetchone()[0] != 2:
                raise PermissionError("existing vault has no complete key binding")
            for purpose, provider in (("encryption", self._encryption_key),
                                      ("receipt", self._receipt_key)):
                commitment = self._commitment(purpose, self._key(provider))
                stored = db.execute("SELECT commitment FROM key_binding WHERE purpose=?",
                                    (purpose,)).fetchone()
                if stored and not hmac.compare_digest(stored[0], commitment):
                    raise PermissionError("vault key changed without an authorized migration")
                if not stored:
                    db.execute("INSERT INTO key_binding VALUES (?,?)", (purpose, commitment))
        self._initialized = True

    @staticmethod
    def _commitment(purpose: str, key: bytes) -> str:
        return hmac.new(key, ("private-stm-receiver-v1:" + purpose).encode("ascii"),
                        hashlib.sha256).hexdigest()

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA secure_delete=ON")
            db.row_factory = sqlite3.Row
            if self._initialized:
                for purpose, provider in (("encryption", self._encryption_key),
                                          ("receipt", self._receipt_key)):
                    binding = db.execute("SELECT commitment FROM key_binding WHERE purpose=?",
                                         (purpose,)).fetchone()
                    expected = self._commitment(purpose, self._key(provider))
                    if binding is None or not hmac.compare_digest(binding[0], expected):
                        raise PermissionError("vault key binding unavailable or changed")
            with db:
                yield db
        finally:
            db.close()

    def _key(self, provider: Callable[[], bytes]) -> bytes:
        key = provider()
        if not isinstance(key, bytes) or len(key) != 32:
            raise PermissionError("protected 256-bit key unavailable")
        return key

    def _token(self, category: str, value: object) -> str:
        material = _canonical({"category": category, "value": value})
        return hmac.new(self._key(self._receipt_key), material, hashlib.sha256).hexdigest()

    def _now(self) -> datetime:
        return _time(self._clock())

    def _allowed(self, action: str, scope: tuple[str, str, str],
                 privacy: str | None, source_id: str | None,
                 target: object | None = None, *, needs_consent: bool = True) -> None:
        try:
            allowed = self._authorize(self.principal, action, scope, privacy,
                                      source_id, target)
            consented = (self._consent(self.principal, action, scope, privacy,
                                       source_id, target) if needs_consent and allowed is True
                         else not needs_consent)
        except Exception as error:
            raise PermissionError("current host authorization/consent unavailable") from error
        if allowed is not True or consented is not True:
            raise PermissionError("current host authorization/consent denied")

    def _target_until(self, target: object) -> datetime:
        if getattr(target, "destination_id", None) != self.destination_id:
            raise PermissionError("unexpected private destination")
        for capability in ("supports_deletion", "supports_correction",
                           "supports_consent_revocation", "private_destination",
                           "supports_scope_isolation"):
            if getattr(target, capability, None) is not True:
                raise PermissionError("target governance is not qualified")
        until = _time(getattr(target, "retention_until", None))
        if until <= self._now():
            raise PermissionError("target retention already expired")
        return until

    def _seal(self, idempotency_key: str, external_id: str, digest: str) -> str:
        return hmac.new(self._key(self._receipt_key), _canonical({
            "destination_id": self.destination_id,
            "idempotency_key": idempotency_key,
            "external_record_id": external_id,
            "source_version_digest": digest,
        }), hashlib.sha256).hexdigest()

    def submit(self, record: object, *, target: object, idempotency_key: str) -> dict:
        """Durably deduplicate a single STM source version, never bypass consent."""
        row = _record_dict(record)
        if row["expires_at"] is None or _time(row["expires_at"]) <= self._now():
            raise PermissionError("source STM record is expired or lacks an expiry")
        if not isinstance(idempotency_key, str) or HEX_64.fullmatch(idempotency_key) is None:
            raise ValueError("STM idempotency key must be an SHA-256 hex digest")
        until = self._target_until(target)
        scope = _scope(row)
        self._allowed("long_term_export", scope, row["privacy_scope"], row["source_id"], target)
        scope_token = self._token("scope", scope)
        source_token = self._token("source", (scope, row["source_id"]))
        turn_token = self._token("turn", (scope, row["turn_id"]))
        privacy_token = self._token("privacy", (scope, row["privacy_scope"]))
        payload = _canonical(row)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM revoked_scopes WHERE scope_token=?", (scope_token,)).fetchone():
                raise PermissionError("scope was revoked")
            if db.execute("SELECT 1 FROM tombstones WHERE scope_token=? AND source_token=?",
                          (scope_token, source_token)).fetchone():
                raise PermissionError("source was erased; re-ingestion is forbidden")
            existing = db.execute("SELECT * FROM records WHERE idempotency_key=?",
                                  (idempotency_key,)).fetchone()
            if existing:
                if (existing["scope_token"] != scope_token
                        or existing["source_version_digest"] != row["source_version_digest"]
                        or existing["erased_at"] is not None
                        or existing["retention_until"] != until.isoformat()):
                    raise PermissionError("idempotency key collision or erased record")
                stored = AESGCM(self._key(self._encryption_key)).decrypt(
                    existing["nonce"], existing["ciphertext"],
                    idempotency_key.encode("ascii"))
                if not hmac.compare_digest(stored, payload):
                    raise PermissionError("idempotency key reused for different payload")
                external_id = existing["external_record_id"]
            else:
                external_id = "dms:" + secrets.token_hex(16)
                nonce = secrets.token_bytes(12)
                ciphertext = AESGCM(self._key(self._encryption_key)).encrypt(
                    nonce, payload, idempotency_key.encode("ascii"))
                db.execute("""INSERT INTO records
                    (idempotency_key, external_record_id, scope_token, source_token,
                     turn_token, privacy_token, source_version_digest, nonce,
                     ciphertext, retention_until) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (idempotency_key, external_id, scope_token, source_token,
                     turn_token, privacy_token, row["source_version_digest"], nonce,
                     ciphertext, until.isoformat()))
                if row["supersedes_id"]:
                    prior = self._token("turn", (scope, row["supersedes_id"]))
                    db.execute("""UPDATE records SET superseded_by=?
                        WHERE scope_token=? AND turn_token=? AND erased_at IS NULL""",
                        (external_id, scope_token, prior))
        return {"destination_id": self.destination_id,
                "source_version_digest": row["source_version_digest"],
                "idempotency_key": idempotency_key,
                "external_record_id": external_id,
                "receipt_mac": self._seal(idempotency_key, external_id,
                                          row["source_version_digest"])}

    def verify_receipt(self, receipt: object, record: object, idempotency_key: str) -> bool:
        """Fresh independent SQLite connection and AEAD readback after commit.

        For full external independence, a separate host verifier must invoke
        this against the actual storage identity; this method alone is not a
        cross-machine or backup qualification.
        """
        row = _record_dict(record)
        if not isinstance(receipt, dict) or receipt.get("idempotency_key") != idempotency_key:
            return False
        external_id = receipt.get("external_record_id")
        if not isinstance(external_id, str) or not external_id.startswith("dms:"):
            return False
        if (receipt.get("destination_id") != self.destination_id or
                receipt.get("source_version_digest") != row["source_version_digest"]):
            return False
        if not hmac.compare_digest(str(receipt.get("receipt_mac", "")), self._seal(
                idempotency_key, external_id, row["source_version_digest"])):
            return False
        scope = _scope(row)
        self._allowed("long_term_read", scope, row["privacy_scope"], row["source_id"])
        with self._connect() as db:
            saved = db.execute("SELECT * FROM records WHERE idempotency_key=? AND external_record_id=?",
                               (idempotency_key, external_id)).fetchone()
            if not saved or saved["erased_at"] or saved["superseded_by"]:
                return False
            if saved["scope_token"] != self._token("scope", scope):
                return False
            if _time(saved["retention_until"]) <= self._now():
                return False
            if db.execute("SELECT 1 FROM revoked_scopes WHERE scope_token=?",
                          (saved["scope_token"],)).fetchone():
                return False
            if db.execute("SELECT 1 FROM tombstones WHERE scope_token=? AND source_token=?",
                          (saved["scope_token"], saved["source_token"])).fetchone():
                return False
            plaintext = AESGCM(self._key(self._encryption_key)).decrypt(
                saved["nonce"], saved["ciphertext"], idempotency_key.encode("ascii"))
            return hmac.compare_digest(plaintext, _canonical(row))

    def erase_source(self, *, scope: tuple[str, str, str], source_id: str) -> int:
        """Authorized target-side erasure and persistent re-ingestion denial."""
        if not isinstance(source_id, str) or not source_id.strip() or len(scope) != 3:
            raise ValueError("exact source and scope required")
        self._allowed("long_term_delete", scope, None, source_id, needs_consent=False)
        scope_token = self._token("scope", scope)
        source_token = self._token("source", (scope, source_id))
        now = self._now().isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO tombstones VALUES (?,?,?)",
                       (scope_token, source_token, now))
            result = db.execute("""UPDATE records SET ciphertext=NULL, nonce=NULL, erased_at=?
                WHERE scope_token=? AND source_token=? AND erased_at IS NULL""",
                (now, scope_token, source_token))
            return result.rowcount

    def revoke_scope(self, *, scope: tuple[str, str, str]) -> int:
        """Withdraw an entire governed owner/agent scope, including retries."""
        if len(scope) != 3 or any(not isinstance(x, str) or not x.strip() for x in scope):
            raise ValueError("exact scope required")
        self._allowed("long_term_revoke", scope, None, None, needs_consent=False)
        token = self._token("scope", scope)
        now = self._now().isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO revoked_scopes VALUES (?,?)", (token, now))
            result = db.execute("""UPDATE records SET ciphertext=NULL, nonce=NULL, erased_at=?
                WHERE scope_token=? AND erased_at IS NULL""", (now, token))
            return result.rowcount

    def expire_due(self) -> int:
        """Host-authorized retention sweep; cannot extend an elapsed deadline."""
        self._allowed("retention_expire", ("*", "*", "*"), None, None,
                      needs_consent=False)
        now = self._now().isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Retention is held in UTC ISO strings with fixed microsecond-free
            # or microsecond-bearing forms; normalize comparison in Python.
            due = db.execute("""SELECT scope_token, source_token, retention_until
                FROM records WHERE erased_at IS NULL""").fetchall()
            expired = [(row["scope_token"], row["source_token"]) for row in due
                       if _time(row["retention_until"]) <= _time(now)]
            count = 0
            for scope_token, source_token in expired:
                db.execute("INSERT OR IGNORE INTO tombstones VALUES (?,?,?)",
                           (scope_token, source_token, now))
                count += db.execute("""UPDATE records SET ciphertext=NULL, nonce=NULL, erased_at=?
                    WHERE scope_token=? AND source_token=? AND erased_at IS NULL""",
                    (now, scope_token, source_token)).rowcount
            return count


__all__ = ["PrivateSTMReceiver", "HISTORICAL_ONLY"]
