import hashlib
import secrets
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from arena_api import config, eval as eval_runner
from arena_api.db import engine, init_db, get_session
from arena_api.models import (
    Challenge, EloRating, EvalRun, JudgeCall, Model, Researcher, utcnow,
)
from arena_api.schemas import (
    ChallengeListOut, ChallengeOut, EvalRunOut, HealthEcho, LeaderboardOut,
    LeaderboardRow, RegisterResearcher, RegisterResearcherOut, SubmitModel, SubmitModelOut,
)

app = FastAPI(title="arena-api", version="0.0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Privacy: silence uvicorn access logs entirely. They include full request paths and would
# leak which models a researcher is poking, when a business uploaded a challenge, etc.
# Use structured logging at the route level for ops if needed; never at the request body level.
import logging as _logging  # noqa: E402
_logging.getLogger("uvicorn.access").disabled = True

@app.on_event("startup")
def _startup():
    init_db()

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def require_researcher(
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
) -> Researcher:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    r = session.exec(select(Researcher).where(Researcher.token_hash == _hash(token))).first()
    if not r:
        raise HTTPException(401, "invalid token")
    return r

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": "0.0.1"}

@app.post("/api/v1/researchers", response_model=RegisterResearcherOut)
def register_researcher(body: RegisterResearcher, session: Session = Depends(get_session)):
    existing = session.exec(select(Researcher).where(Researcher.email == body.email)).first()
    if existing:
        raise HTTPException(409, "email already registered")
    token = "rsh_" + secrets.token_urlsafe(24)
    r = Researcher(email=body.email, name=body.name, affiliation=body.affiliation, token_hash=_hash(token))
    session.add(r); session.commit(); session.refresh(r)
    return RegisterResearcherOut(id=r.id, email=r.email, name=r.name, token=token)

@app.post("/api/v1/models", response_model=SubmitModelOut)
def submit_model(
    body: SubmitModel,
    bg: BackgroundTasks,
    researcher: Researcher = Depends(require_researcher),
    session: Session = Depends(get_session),
):
    if body.field not in ("text", "code", "vision", "audio", "science"):
        raise HTTPException(400, "unknown field")
    if body.protocol_version != "v0":
        raise HTTPException(400, "unsupported protocol_version")

    # Probe /health synchronously — fail fast if endpoint is dead.
    health_echo: Optional[HealthEcho] = None
    endpoint_status = "unreachable"
    try:
        headers = {"content-type": "application/json"}
        if body.auth_header:
            headers["authorization"] = body.auth_header
        r = httpx.get(body.endpoint_url.rstrip("/") + "/health", headers=headers, timeout=config.HEALTH_TIMEOUT_S)
        if r.status_code == 200:
            data = r.json()
            health_echo = HealthEcho(**{k: data.get(k) for k in ("status", "model_name", "model_version", "gpu_available", "gpu_name")})
            endpoint_status = "healthy" if (health_echo.status or "").lower() == "ok" else "unreachable"
    except Exception:
        pass

    m = Model(
        researcher_id=researcher.id, field=body.field, name=body.name, version=body.version,
        endpoint_url=body.endpoint_url, auth_header=body.auth_header, description=body.description,
        repo_url=body.repo_url, paper_url=body.paper_url, status=endpoint_status,
    )
    session.add(m); session.commit(); session.refresh(m)

    # Ensure Elo row exists
    elo = session.exec(select(EloRating).where(EloRating.model_id == m.id, EloRating.field == m.field)).first()
    if not elo:
        session.add(EloRating(model_id=m.id, field=m.field))
        session.commit()

    eval_run_id: Optional[int] = None
    if endpoint_status == "healthy":
        # Prefer encrypted held-out; fall back to plaintext only for dev
        holdout_dir = Path(__file__).resolve().parent.parent / "data" / "holdouts"
        candidates = [holdout_dir / f"{m.field}.jsonl.enc", holdout_dir / f"{m.field}.jsonl"]
        chosen = next((c for c in candidates if c.exists()), None)
        if chosen is not None:
            er = EvalRun(model_id=m.id, status="queued", rows_total=0)
            session.add(er); session.commit(); session.refresh(er)
            eval_run_id = er.id
            bg.add_task(_kick_eval, er.id, m.id, str(chosen))

    return SubmitModelOut(
        model_id=m.id,
        eval_run_id=eval_run_id,
        endpoint_status=endpoint_status,
        endpoint_health=health_echo,
    )

def _kick_eval(eval_run_id: int, model_id: int, holdout_path: str):
    import asyncio
    asyncio.run(eval_runner.run_eval(eval_run_id, model_id, holdout_path))

@app.get("/api/v1/eval-runs/{run_id}", response_model=EvalRunOut)
def get_eval_run(run_id: int, session: Session = Depends(get_session)):
    er = session.get(EvalRun, run_id)
    if not er:
        raise HTTPException(404, "not found")
    return EvalRunOut(
        id=er.id, model_id=er.model_id, challenge_id=er.challenge_id, status=er.status,
        rows_total=er.rows_total, rows_passed=er.rows_passed, score=er.score, error=er.error,
        started_at=er.started_at, finished_at=er.finished_at,
    )

@app.get("/api/v1/leaderboard/{field}", response_model=LeaderboardOut)
def leaderboard(field: str, session: Session = Depends(get_session)):
    elos = session.exec(select(EloRating).where(EloRating.field == field)).all()
    rows: list[LeaderboardRow] = []
    for e in elos:
        m = session.get(Model, e.model_id)
        if not m: continue
        r = session.get(Researcher, m.researcher_id)
        # latest complete eval_run for this model on this field
        er = session.exec(
            select(EvalRun).where(EvalRun.model_id == m.id, EvalRun.status == "complete").order_by(EvalRun.id.desc())
        ).first()
        rows.append(LeaderboardRow(
            rank=0, model_id=m.id, model_name=f"{m.name} v{m.version}",
            researcher_name=r.name if r else "unknown",
            elo=e.rating, benchmark_score=er.score if er else None, n_matches=e.n_matches,
        ))
    rows.sort(key=lambda x: x.elo, reverse=True)
    for i, r in enumerate(rows, start=1):
        r.rank = i
    return LeaderboardOut(field=field, rows=rows)

@app.get("/api/v1/challenges", response_model=ChallengeListOut)
def list_challenges(field: Optional[str] = None, session: Session = Depends(get_session)):
    q = select(Challenge).where(Challenge.status == "open")
    if field:
        q = q.where(Challenge.field == field)
    items = session.exec(q).all()
    return ChallengeListOut(
        items=[ChallengeOut(
            id=c.id, field=c.field, title=c.title, description=c.description,
            bounty_usd=c.bounty_usd, status=c.status, created_at=c.created_at,
        ) for c in items],
        total=len(items),
    )

@app.get("/api/v1/my/models")
def my_models(researcher: Researcher = Depends(require_researcher), session: Session = Depends(get_session)):
    ms = session.exec(select(Model).where(Model.researcher_id == researcher.id)).all()
    return [{"id": m.id, "name": m.name, "version": m.version, "field": m.field, "status": m.status} for m in ms]
