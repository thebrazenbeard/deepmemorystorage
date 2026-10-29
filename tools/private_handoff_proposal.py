"""Validate private historical-memory handoff proposals without persisting them.

The public DeepMemoryStorage repository is never an implicit private writer.
Validated proposals are NOT acceptance receipts or current-memory admission.
"""
from dataclasses import dataclass
import hashlib
import json
import re

_SHA=re.compile(r"[0-9a-f]{64}\Z")
_IDENT=re.compile(r"[A-Za-z0-9_:.@-]{2,256}\Z")

class HandoffError(ValueError):
    pass

def _id(s,label):
    if type(s) is not str or not _IDENT.fullmatch(s):
        raise HandoffError("invalid "+label)
    return s

@dataclass(frozen=True)
class PrivateHandoffProposal:
    owner_id: str
    source_id: str
    source_sha256: str
    admission_decision_id: str
    consent_receipt_id: str
    source_privacy_scope: str
    destination: str
    event_time_status: str
    memory_class: str = "HISTORICAL_AUDIT"
    currentness_rule: str = "REVALIDATE_BEFORE_CURRENT_USE"
    correction_of: str | None = None
    revocation_of: str | None = None
    retention_policy_id: str | None = None

    def __post_init__(self):
        for attr in ("owner_id","source_id","admission_decision_id",
                     "consent_receipt_id","source_privacy_scope","destination",
                     "event_time_status"):
            _id(getattr(self,attr),attr)
        if not _SHA.fullmatch(self.source_sha256):
            raise HandoffError("invalid source fingerprint")
        if self.destination != "private_host_vault":
            raise HandoffError("private host storage only; public Git is prohibited")
        if self.memory_class not in ("AUTOBIOGRAPHICAL","WORKING_PROJECT","HISTORICAL_AUDIT"):
            raise HandoffError("unknown historical memory class")
        if self.currentness_rule != "REVALIDATE_BEFORE_CURRENT_USE":
            raise HandoffError("historical evidence cannot claim currentness")
        if self.source_privacy_scope in ("public","unknown","none"):
            raise HandoffError("explicit private scope required")
        if self.retention_policy_id is None:
            raise HandoffError("explicit target retention policy required")
        _id(self.retention_policy_id,"retention policy")
        if self.correction_of and self.revocation_of:
            raise HandoffError("separate correction/revocation events required")
        if self.correction_of:_id(self.correction_of,"correction target")
        if self.revocation_of:_id(self.revocation_of,"revocation target")

    @property
    def proposal_digest(self):
        payload=json.dumps(vars(self),sort_keys=True,separators=(",",":")).encode()
        return hashlib.sha256(b"dms.private.handoff.v1\0"+payload).hexdigest()

    @property
    def is_durable(self):
        return False

    @property
    def admission_granted(self):
        return False

    def required_readback(self):
        return {
            "proposal_digest":self.proposal_digest,
            "required_destination":"private_host_vault",
            "required_evidence":("encrypted_write_receipt",
                                "independent_decrypt_readback",
                                "owner_scope_authorization",
                                "retention_and_revocation_controller"),
            "status":"NOT_WRITTEN"
        }
