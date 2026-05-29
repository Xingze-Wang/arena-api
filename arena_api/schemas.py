from typing import Optional, Any
from pydantic import BaseModel, Field

class RegisterResearcher(BaseModel):
    email: str
    name: str
    affiliation: Optional[str] = None

class RegisterResearcherOut(BaseModel):
    id: int
    email: str
    name: str
    token: str  # returned once; store it

class SubmitModel(BaseModel):
    protocol_version: str = "v0"
    field: str  # text|code|vision|audio|science
    name: str
    version: str
    endpoint_url: str
    auth_header: Optional[str] = None
    description: Optional[str] = None
    repo_url: Optional[str] = None
    paper_url: Optional[str] = None

class HealthEcho(BaseModel):
    status: str
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    gpu_available: Optional[bool] = None
    gpu_name: Optional[str] = None

class SubmitModelOut(BaseModel):
    model_id: int
    eval_run_id: Optional[int] = None
    endpoint_status: str  # healthy|unreachable
    endpoint_health: Optional[HealthEcho] = None

class EvalRunOut(BaseModel):
    id: int
    model_id: int
    challenge_id: Optional[int]
    status: str
    rows_total: int
    rows_passed: int
    score: Optional[float]
    error: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]

class LeaderboardRow(BaseModel):
    rank: int
    model_id: int
    model_name: str
    researcher_name: str
    elo: float
    benchmark_score: Optional[float] = None
    n_matches: int

class LeaderboardOut(BaseModel):
    field: str
    rows: list[LeaderboardRow]

class ChallengeOut(BaseModel):
    id: int
    field: str
    title: str
    description: Optional[str]
    bounty_usd: int
    status: str
    created_at: str

class ChallengeListOut(BaseModel):
    items: list[ChallengeOut]
    total: int
