"""Eval runner — calls a researcher's /predict against a held-out set, judges with Anthropic.

Trust boundary: held-out rows live in arena's DB. We send ONLY `input` to the researcher.
The reference answer never leaves this process — goes straight from disk into the judge prompt.
"""
import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from datetime import datetime


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

import httpx
from anthropic import AsyncAnthropic
from sqlmodel import Session, select

from arena_api import config
from arena_api.crypto import read_rows
from arena_api.db import engine
from arena_api.models import EvalRun, JudgeCall, Model, utcnow

_judge_system_prompt = (
    "You are a strict grader for a model benchmark. You will be given a Question, a Reference Answer, "
    "and a Candidate Answer. Decide if the Candidate matches the Reference in meaning. Be terse and fair: "
    "a candidate that says the same thing differently is a pass; a candidate that hedges with extra "
    "speculation that contradicts the reference is partial; a candidate that gets the core fact wrong is fail. "
    "Return ONLY a JSON object on a single line:\n"
    '{"verdict":"pass|fail|partial","score":<0..1>,"rationale":"<one sentence>"}'
)

def _extract_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        for k in ("text", "answer", "output", "completion"):
            if k in output and isinstance(output[k], str):
                return output[k]
        return json.dumps(output)
    return str(output)

def _parse_judge_json(s: str) -> dict:
    s = s.strip()
    # strip code fences
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.MULTILINE).strip()
    # take first { ... } block
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        s = m.group(0)
    obj = json.loads(s)
    verdict = str(obj.get("verdict", "fail")).lower()
    if verdict not in ("pass", "fail", "partial"):
        verdict = "fail"
    score = float(obj.get("score", 0.0))
    score = max(0.0, min(1.0, score))
    return {"verdict": verdict, "score": score, "rationale": str(obj.get("rationale", ""))[:500]}


async def _predict_one(client: httpx.AsyncClient, url: str, auth: str | None, input_payload: Any) -> tuple[str, float, str | None]:
    headers = {"content-type": "application/json"}
    if auth:
        headers["authorization"] = auth
    body = {"input": input_payload}
    t0 = time.time()
    try:
        r = await client.post(url.rstrip("/") + "/predict", json=body, headers=headers, timeout=config.PREDICT_TIMEOUT_S)
        latency = (time.time() - t0) * 1000
        if r.status_code != 200:
            return "", latency, f"http {r.status_code}: {r.text[:200]}"
        data = r.json()
        return _extract_text(data.get("output", "")), latency, None
    except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
        return "", (time.time() - t0) * 1000, f"network: {type(e).__name__}: {e}"


async def _judge_one(anthropic: AsyncAnthropic, question: str, reference: str, candidate: str) -> dict:
    if not candidate:
        return {"verdict": "fail", "score": 0.0, "rationale": "empty candidate"}
    msg = (
        f"Question: {question}\n"
        f"Reference Answer: {reference}\n"
        f"Candidate Answer: {candidate}"
    )
    resp = await anthropic.messages.create(
        model=config.JUDGE_MODEL,
        max_tokens=config.JUDGE_MAX_TOKENS,
        system=[{"type": "text", "text": _judge_system_prompt, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": msg}],
    )
    text = resp.content[0].text if resp.content else "{}"
    try:
        return _parse_judge_json(text)
    except Exception as e:
        return {"verdict": "fail", "score": 0.0, "rationale": f"judge-parse-error: {e}"}


async def run_eval(eval_run_id: int, model_id: int, holdout_path: str) -> None:
    """Background task. Loads .jsonl rows, hits /predict for each, judges, writes results."""
    p = Path(holdout_path)
    if not p.exists():
        with Session(engine) as s:
            er = s.get(EvalRun, eval_run_id)
            er.status = "failed"
            er.error = "holdout file missing"  # never include the path in error text — could leak filenames
            er.finished_at = utcnow()
            s.add(er); s.commit()
        return
    # Decryption happens in-memory only; rows never re-touch disk in plaintext.
    rows: list[dict] = read_rows(p)

    with Session(engine) as s:
        er = s.get(EvalRun, eval_run_id)
        m = s.get(Model, model_id)
        er.status = "running"
        er.started_at = utcnow()
        er.rows_total = len(rows)
        s.add(er); s.commit()
        endpoint_url = m.endpoint_url
        auth = m.auth_header

    anthropic = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None
    judge_sem = asyncio.Semaphore(config.JUDGE_CONCURRENCY)

    async with httpx.AsyncClient() as http:
        # 1) predict all rows
        pred_tasks = [_predict_one(http, endpoint_url, auth, r["input"]) for r in rows]
        preds = await asyncio.gather(*pred_tasks)

        # 2) judge in parallel, bounded
        async def judge_row(i: int, row: dict, cand: str, latency_ms: float, err: str | None):
            async with judge_sem:
                if err:
                    return i, {"verdict": "fail", "score": 0.0, "rationale": f"endpoint error: {err}"}, latency_ms
                if anthropic is None:
                    # No API key — score by exact-substring match so the demo still runs
                    ref = str(row.get("reference", "")).lower().strip()
                    ok = ref and ref in cand.lower()
                    return i, {"verdict": "pass" if ok else "fail", "score": 1.0 if ok else 0.0, "rationale": "no-judge fallback"}, latency_ms
                v = await _judge_one(anthropic, str(row["input"]), str(row.get("reference", "")), cand)
                return i, v, latency_ms

        judge_tasks = [
            judge_row(i, rows[i], preds[i][0], preds[i][1], preds[i][2])
            for i in range(len(rows))
        ]
        results = await asyncio.gather(*judge_tasks)

    # 3) persist
    passed = 0
    total_score = 0.0
    with Session(engine) as s:
        for i, verdict, latency in results:
            row = rows[i]
            cand = preds[i][0]
            # Store hashes only — never plaintext content. Rationale is heavily truncated.
            jc = JudgeCall(
                eval_run_id=eval_run_id,
                row_index=i,
                input_hash=_h(str(row["input"])),
                output_hash=_h(cand),
                reference_hash=_h(str(row.get("reference", ""))),
                verdict=verdict["verdict"],
                score=verdict["score"],
                rationale_redacted=verdict["rationale"][:80],
                latency_ms=latency,
            )
            s.add(jc)
            if verdict["verdict"] == "pass":
                passed += 1
            total_score += verdict["score"]
        er = s.get(EvalRun, eval_run_id)
        er.status = "complete"
        er.finished_at = utcnow()
        er.rows_passed = passed
        er.score = (total_score / max(1, len(rows))) * 100.0
        s.add(er); s.commit()
