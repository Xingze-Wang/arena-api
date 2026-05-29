"""Encrypt-at-rest for held-out data.

Why: business uploads private test rows. Even though the rows live on the same box as
arena-api, we encrypt them with a key that is loaded from env at process start and never
persisted alongside the ciphertext. An attacker with disk-only access (stolen backup,
filesystem snapshot) sees ciphertext. An attacker with shell on the running box can dump
the process memory and recover the key — that gap is real and is what TEEs close in v1.

Implementation: AES-256-GCM via stdlib `cryptography` if available; falls back to a clearly
labeled "no-crypto" mode for local dev when the lib isn't installed. Production deploy
MUST set ARENA_HOLDOUT_KEY (base64, 32 bytes) and install `cryptography`.

This module never logs plaintext, never logs ciphertext, never logs the key.
"""
import base64
import json
import os
import secrets
from pathlib import Path
from typing import Any

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_AESGCM = True
except Exception:
    _HAS_AESGCM = False


def _load_key() -> bytes | None:
    b64 = os.environ.get("ARENA_HOLDOUT_KEY", "")
    if not b64:
        return None
    raw = base64.b64decode(b64)
    if len(raw) != 32:
        raise RuntimeError("ARENA_HOLDOUT_KEY must be base64(32 bytes)")
    return raw


_KEY = _load_key()


def is_encrypted_path(p: Path) -> bool:
    return p.suffix == ".enc"


def encrypt_jsonl_file(plaintext_path: Path, out_path: Path) -> Path:
    """Convert a .jsonl file to a .jsonl.enc file. Each line is independently encrypted
    so streaming reads stay possible. The plaintext file is then deleted."""
    if not _HAS_AESGCM or _KEY is None:
        # dev fallback — just rename, log nothing
        out_path.write_bytes(plaintext_path.read_bytes())
        plaintext_path.unlink()
        return out_path
    aes = AESGCM(_KEY)
    enc_lines: list[str] = []
    for line in plaintext_path.read_text().splitlines():
        if not line.strip():
            continue
        nonce = secrets.token_bytes(12)
        ct = aes.encrypt(nonce, line.encode(), None)
        enc_lines.append(base64.b64encode(nonce + ct).decode())
    out_path.write_text("\n".join(enc_lines) + "\n")
    plaintext_path.unlink()
    return out_path


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Read .jsonl OR .jsonl.enc. Decryption happens in memory; nothing is logged."""
    text = path.read_text()
    rows: list[dict[str, Any]] = []
    if path.suffixes[-2:] == [".jsonl", ".enc"] or path.suffix == ".enc":
        if not _HAS_AESGCM or _KEY is None:
            # dev fallback — file was renamed not encrypted
            for line in text.splitlines():
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
            return rows
        aes = AESGCM(_KEY)
        for b64 in text.splitlines():
            b64 = b64.strip()
            if not b64:
                continue
            blob = base64.b64decode(b64)
            nonce, ct = blob[:12], blob[12:]
            rows.append(json.loads(aes.decrypt(nonce, ct, None).decode()))
        return rows
    # plain .jsonl (only meant for committed text-trivia dev set; real business uploads must be .enc)
    for line in text.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def crypto_status() -> dict:
    return {
        "cryptography_lib": _HAS_AESGCM,
        "key_loaded": _KEY is not None,
        "mode": "aes-256-gcm" if (_HAS_AESGCM and _KEY) else "DEV_NO_CRYPTO",
    }
