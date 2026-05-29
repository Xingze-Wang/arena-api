# Threat Model — arena v0

Two parties trust the arena with sensitive data:

- **Businesses** upload private held-out test sets. If a researcher (or a competitor) gets the set, every model's "score" becomes meaningless.
- **Researchers** expose their model outputs to the arena (and the judge). If those outputs leak to competing labs or to the business before a payout, a researcher loses negotiation leverage.

The arena's goal: **neither party sees the other's data, and the platform operator sees as little as technically possible.**

This document is honest about what v0 achieves and what it doesn't.

---

## What v0 enforces

### Held-out test rows
- Encrypted at rest with AES-256-GCM. Key (`ARENA_HOLDOUT_KEY`, base64 of 32 bytes) lives in environment, not on disk next to the ciphertext.
- The arena process reads, decrypts in memory, sends `input` only to the researcher's `/predict`. The `reference_answer` field never leaves the arena process — it goes directly into the judge prompt and is discarded.
- Researchers never see the reference. They see only their aggregate score and a per-row pass/fail bit.

### Researcher model outputs
- Outputs go to the LLM judge (Anthropic) for scoring, then are **discarded**. They are not written to disk.
- The audit row (`judge_calls` table) stores **SHA-256 hashes** of `input`, `output`, and `reference` — not the plaintext. Provides dispute auditability ("yes, this exact output was scored against this exact reference") without revealing content.
- Judge rationale is truncated to 80 characters in the audit row to limit content leakage.

### Logging
- Uvicorn access logs are disabled (`uvicorn.access` logger off). Request paths, query strings, and bodies are never written.
- The eval runner does not print or log row content under any condition. On error it records a type tag (e.g., `"network: TimeoutException"`) — never the input or output.
- Holdout file paths are not echoed in error messages.

### Researcher endpoint isolation
- The arena calls the researcher's `/predict` URL with HTTP only — no credentials are sent (unless the researcher set `auth_header` in their submission, which is the researcher's own token, not arena secrets).
- Endpoints are treated as untrusted: bounded timeouts, no retry storms, no follow of redirects to internal hosts.

### Token storage
- Researcher tokens are stored as SHA-256 hashes. The plaintext token is returned to the researcher exactly once at registration and never written back.

---

## What v0 does NOT enforce — and where the residual risk is

An attacker with shell on the arena-api host (the "platform operator") can:

1. **Dump the running process's memory** and recover `ARENA_HOLDOUT_KEY`, then decrypt held-out files on disk. There is no way around this without a TEE — RAM is shared with whoever runs the box.
2. **Inject code into the running arena-api** that logs `model_input`, `model_output`, or `reference` before they hit the hash. The code in this repo never does that; a malicious operator can edit the code.
3. **Tap the network** between the arena and the researcher's endpoint (the request body contains `input` plaintext over HTTPS). Mitigated by TLS in transit; only matters at the host edge.
4. **Subpoena**. Encrypt-at-rest and process-memory secrets do nothing against legal demand. Operator policy must address this separately.

So today the strongest honest claim is: **"the arena, as written, does not expose either side's data to the other party, and the operator's exposure is reduced to in-memory transient state during eval."** Not zero. Reduced.

---

## v1 path — closing the operator gap

To make the platform operator truly blind requires hardware-rooted isolation:

1. **AWS Nitro Enclaves** for the eval worker. The enclave attests its code hash to the business before the business uploads the held-out set. The business encrypts the set with a key bound to the enclave's attestation — only that specific enclave image can decrypt. Operator's root account on the EC2 host cannot peek into enclave memory.
2. **Customer-side encryption of submissions.** The researcher's `/predict` request body could optionally be wrapped in a per-call symmetric key that only the enclave holds. The hosting box (between TLS termination and the enclave) sees ciphertext only.
3. **Bring-your-own-judge.** Instead of Anthropic's hosted judge, support submitting a frozen judge model into the same enclave. Removes the cloud LLM as a data-exfiltration risk.
4. **Hash-chained audit log.** Each `judge_calls` row is anchored into a hash chain published daily so the operator can't quietly rewrite history.

None of (1)–(4) are in v0 because each is multi-week work. They are the explicit milestone for v1.

---

## How users should interpret v0

- A small business should be willing to upload a held-out set if their alternative is "give the data to one researcher and trust them." The arena's hashed audit and silent logs are strictly better than email-the-CSV.
- A small business should NOT upload data covered by regulated-content rules (PHI, EU personal data) until v1 with Nitro Enclaves is shipped and audited.
- A researcher should treat their `/predict` as exposed-to-arena. Don't put model weights or proprietary intermediate state in the response — return only what scoring needs.
- Both sides should read the audit table after their eval. If something looks off (row count mismatch, hashes that don't match what they expect), file an issue.

---

## How to verify the claims in this doc

- `grep -rn 'logger\|print\|logging' arena_api/eval.py` — eval runner should have zero plaintext-content prints.
- `grep -n 'model_input\|model_output\|reference' arena_api/models.py` — should not appear as plaintext columns; only `*_hash` columns exist.
- Inspect the running DB: `sqlite3 data/arena.db 'select * from judgecall limit 1'` should show hex hashes, not English.
- `curl localhost:8001/api/v1/crypto/status` (admin-only — not yet wired) will report whether the key is loaded and crypto is active.

If anything in this doc is contradicted by the code, the code is wrong. File an issue.
