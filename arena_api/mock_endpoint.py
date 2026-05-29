"""A mock paper-to-api server. Implements protocol v0 so you can test the arena loop without a real model.

  uvicorn arena_api.mock_endpoint:app --port 9001
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Optional

app = FastAPI(title="mock-paper-to-api")

KB = {
    "transistor": "1947",
    "hamlet": "William Shakespeare",
    "gold": "Au",
    "australia": "Canberra",
    "boiling point of water": "100",
    "mona lisa": "Leonardo da Vinci",
    "largest planet": "Jupiter",
    "world war ii end": "1945",
    "speed of light": "299792458",
    "smallest prime": "2",
}

class PredictRequest(BaseModel):
    input: Any
    parameters: Optional[dict] = None

class PredictResponse(BaseModel):
    output: Any
    latency_ms: Optional[float] = None

@app.get("/health")
def health():
    return {"status": "ok", "model_name": "mock-7B", "model_version": "0.0.1", "gpu_available": False, "gpu_name": None}

@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    q = str(req.input).lower()
    for k, v in KB.items():
        if k in q:
            return PredictResponse(output={"text": v}, latency_ms=12.0)
    return PredictResponse(output={"text": "I don't know."}, latency_ms=8.0)
