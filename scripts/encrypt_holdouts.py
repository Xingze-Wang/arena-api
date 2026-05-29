"""One-shot: convert any data/holdouts/*.jsonl into data/holdouts/*.jsonl.enc.
Run after setting ARENA_HOLDOUT_KEY. Idempotent (skips already-encrypted files)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arena_api.crypto import encrypt_jsonl_file, _KEY, _HAS_AESGCM

if not (_HAS_AESGCM and _KEY):
    print("ARENA_HOLDOUT_KEY not set or cryptography missing — refusing.")
    sys.exit(1)

root = Path(__file__).resolve().parent.parent / "data" / "holdouts"
for p in root.glob("*.jsonl"):
    out = p.with_suffix(p.suffix + ".enc")
    encrypt_jsonl_file(p, out)
    print(f"encrypted: {p.name} -> {out.name}")
