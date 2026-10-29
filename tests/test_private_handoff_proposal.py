import hashlib
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from private_handoff_proposal import PrivateHandoffProposal,HandoffError

def proposal(**overrides):
    base=dict(owner_id="owner_private",source_id="chatgpt:synthetic",
              source_sha256=hashlib.sha256(b"synthetic").hexdigest(),
              admission_decision_id="decision:receipt-1",
              consent_receipt_id="consent:receipt-1",
              source_privacy_scope="owner_private",
              destination="private_host_vault",
              event_time_status="HISTORICAL_EVENT_TIME_UNKNOWN",
              retention_policy_id="policy:private-historical-1")
    base.update(overrides)
    return PrivateHandoffProposal(**base)

class PrivateHandoffTests(unittest.TestCase):
    def test_proposal_has_no_false_receipt_or_currentness(self):
        p=proposal()
        self.assertFalse(p.is_durable)
        self.assertFalse(p.admission_granted)
        self.assertEqual(p.required_readback()["status"],"NOT_WRITTEN")
        self.assertEqual(p.currentness_rule,"REVALIDATE_BEFORE_CURRENT_USE")

    def test_public_github_destination_rejected(self):
        for bad in ("public_github","https:github.com/repo","",
                    "deepmemorystorage_public"):
            with self.subTest(bad=bad),self.assertRaises(HandoffError):
                proposal(destination=bad)

    def test_unknown_or_public_scope_rejected(self):
        for scope in ("public","unknown","none"):
            with self.subTest(scope=scope),self.assertRaises(HandoffError):
                proposal(source_privacy_scope=scope)

    def test_missing_retention_policy_denied(self):
        with self.assertRaises(HandoffError):
            proposal(retention_policy_id=None)

    def test_cannot_self_promote_currentness(self):
        with self.assertRaises(HandoffError):
            proposal(currentness_rule="CURRENT")

    def test_idempotent_digests(self):
        a,b=proposal(),proposal()
        c=proposal(source_id="chatgpt:synthetic2")
        self.assertEqual(a.proposal_digest,b.proposal_digest)
        self.assertNotEqual(a.proposal_digest,c.proposal_digest)

    def test_correction_and_revocation_are_distinct(self):
        p=proposal(correction_of="memory:old")
        self.assertEqual(p.correction_of,"memory:old")
        with self.assertRaises(HandoffError):
            proposal(correction_of="memory:old",revocation_of="memory:old")

    def test_source_hash_and_ids_required(self):
        with self.assertRaises(HandoffError):
            proposal(source_sha256="bad")
        with self.assertRaises(HandoffError):
            proposal(source_id="../../private/secret")

if __name__=="__main__": unittest.main()
