# Private handoff proposals for ChatGPT account history (source only)

Event: `chat_history_ingestion_live_coordination`.

The public `deepmemorystorage` repository is historical **source architecture**, not an authorized upload target for private conversations. This change adds a small machine-validatable *proposal contract* at `tools/private_handoff_proposal.py` for a separately provisioned private host-owned encrypted target. No real ChatGPT text or account export is committed.

A proposal includes owner namespace, source ID/digest, reviewed historical admission decision and consent receipt, source privacy scope, time uncertainty, historical memory class, an explicit target retention policy, and optionally correction or revocation target. It rejects public destinations, absent retention, unknown scope, invalid hashes or claimed current authority.

**A validated proposal is not a write or a receipt.** `required_readback()` says `NOT_WRITTEN` until a private writer produces and independently verifies the encrypted readback, idempotence, correction/deletion propagation, and owner-scoped authorization. The record remains historical, never live Lantern currentness or model identity.

The opt-in STM 30-day review / 45-day expiration governance applies only when explicitly attached to a qualifying *new-conversation* retention policy. It must not silently re-age the user's historical account export or give private DMS eternal retention.

```powershell
py -3 -m unittest discover -s tests -p 'test_private_handoff_proposal.py' -v
```

The GitHub repository's existing public ledger tranches and historical index remain untouched.
