from fastapi import FastAPI, HTTPException

from .decision import classify_decision
from .models import (
    Availability,
    DecisionClassification,
    DecisionRequest,
    ModelCandidate,
    QuotaObservation,
    RouteRequest,
)
from .quota import classify_observation
from .router import NoEligibleModel, select_candidate

app = FastAPI(title="Hermes Forge Controller", version="0.1.0")

# M0 uses an in-memory catalogue so domain behaviour is executable before persistence lands.
_candidates: list[ModelCandidate] = []


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/quota/classify", response_model=Availability)
def quota_classify(observation: QuotaObservation) -> Availability:
    return classify_observation(observation)


@app.put("/v1/candidates", response_model=list[ModelCandidate])
def replace_candidates(candidates: list[ModelCandidate]) -> list[ModelCandidate]:
    _candidates[:] = candidates
    return _candidates


@app.post("/v1/route", response_model=ModelCandidate)
def route(request: RouteRequest) -> ModelCandidate:
    try:
        return select_candidate(request, _candidates)
    except NoEligibleModel as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/decisions/classify", response_model=DecisionClassification)
def decision_classify(request: DecisionRequest) -> DecisionClassification:
    return classify_decision(request)
