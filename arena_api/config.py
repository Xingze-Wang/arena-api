import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("ARENA_DB_PATH", str(ROOT / "data" / "arena.db"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-opus-4-7")
HEALTH_TIMEOUT_S = 10
PREDICT_TIMEOUT_S = 30
JUDGE_MAX_TOKENS = 400
JUDGE_CONCURRENCY = 4
K_FACTOR = 32
