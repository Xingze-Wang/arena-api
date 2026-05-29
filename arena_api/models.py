from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field

def utcnow() -> str:
    return datetime.utcnow().isoformat()

class Researcher(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str
    affiliation: Optional[str] = None
    token_hash: str = Field(index=True)
    created_at: str = Field(default_factory=utcnow)

class Model(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    researcher_id: int = Field(foreign_key="researcher.id", index=True)
    field: str = Field(index=True)  # text|code|vision|audio|science
    name: str
    version: str
    endpoint_url: str
    auth_header: Optional[str] = None
    description: Optional[str] = None
    repo_url: Optional[str] = None
    paper_url: Optional[str] = None
    status: str = "pending"  # pending|healthy|unreachable
    created_at: str = Field(default_factory=utcnow)

class Challenge(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    field: str = Field(index=True)
    business_email: str
    title: str
    description: Optional[str] = None
    bounty_usd: int = 0
    holdout_path: str  # path to a .jsonl
    status: str = "open"  # open|closed
    created_at: str = Field(default_factory=utcnow)

class EvalRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    model_id: int = Field(foreign_key="model.id", index=True)
    challenge_id: Optional[int] = Field(default=None, foreign_key="challenge.id", index=True)
    status: str = "queued"  # queued|running|complete|failed
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    rows_total: int = 0
    rows_passed: int = 0
    score: Optional[float] = None
    error: Optional[str] = None
    created_at: str = Field(default_factory=utcnow)

class JudgeCall(SQLModel, table=True):
    """Audit trail. Stores HASHES of the inputs/outputs, not the plaintext.

    Why hashes: the platform operator (someone with shell on the box) can read the
    arena DB. Storing plaintext model_input, model_output, or reference would let the
    operator reconstruct held-out test sets and steal model outputs. Hashes let us
    prove later "yes, this exact row was scored against this exact reference and got
    this verdict" without exposing content.

    Rationale is truncated to 80 chars to limit content leakage in the audit row.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    eval_run_id: int = Field(foreign_key="evalrun.id", index=True)
    row_index: int
    input_hash: str
    output_hash: str
    reference_hash: str
    verdict: str
    score: float
    rationale_redacted: str  # max 80 chars, see eval.py
    latency_ms: float = 0.0
    created_at: str = Field(default_factory=utcnow)

class EloRating(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    model_id: int = Field(foreign_key="model.id", index=True)
    field: str = Field(index=True)
    rating: float = 1200.0
    n_matches: int = 0
    updated_at: str = Field(default_factory=utcnow)

class Vote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    field: str = Field(index=True)
    model_a_id: int = Field(foreign_key="model.id")
    model_b_id: int = Field(foreign_key="model.id")
    winner: str  # a|b|tie
    prompt: str
    output_a: str
    output_b: str
    voter_fingerprint: str
    created_at: str = Field(default_factory=utcnow)
