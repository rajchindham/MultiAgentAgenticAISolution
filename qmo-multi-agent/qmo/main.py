import asyncio
import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from qmo.models import Ask
from qmo.model import DemoModel, OpenAIModel
from qmo.repository import DashboardRAGRepository, EnterpriseRepository
from qmo.legacy_rag.core import init_db
from qmo.graph import build_graph, initial

load_dotenv()
log = logging.getLogger(__name__)
bearer = HTTPBearer(auto_error=False)

@asynccontextmanager
async def lifespan(app):
    mode = os.getenv("QMO_MODE", "demo")
    if mode not in ("demo", "openai"):
        raise RuntimeError("QMO_MODE must be demo or openai")
    if not os.getenv("QMO_API_TOKEN"):
        raise RuntimeError("Set QMO_API_TOKEN before starting the API")
    if mode == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY for OpenAI mode")
    await asyncio.to_thread(init_db)
    model = OpenAIModel(os.getenv("QMO_MODEL", "gpt-4.1-mini")) if mode == "openai" else DemoModel()
    backend = os.getenv("QMO_DATA_BACKEND", "sample")
    if backend not in ("sample", "enterprise"):
        raise RuntimeError("QMO_DATA_BACKEND must be sample or enterprise")
    if backend == "enterprise" and mode != "openai":
        raise RuntimeError("Enterprise adapter requires OpenAI embeddings")
    repo = EnterpriseRepository(model.client) if backend == "enterprise" else DashboardRAGRepository()
    app.state.graph = build_graph(model, repo)
    try:
        yield
    finally:
        await model.close()

app = FastAPI(title="QMO Multi-Agent Scorecard", lifespan=lifespan)

def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    expected = os.getenv("QMO_API_TOKEN", "")
    if not expected or not credentials or not secrets.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, "Invalid bearer token")
    return {"portfolio": os.getenv("QMO_ALLOWED_PORTFOLIO", "Digital Platforms"),
            "applications": set(os.getenv("QMO_ALLOWED_APPLICATIONS", "Mobile App,Web Check-in").split(","))}

def input_for(request, principal):
    if request.application not in principal["applications"]:
        raise HTTPException(403, "Application access denied")
    if request.previous_period and request.previous_period >= request.period:
        raise HTTPException(422, "previous_period must be earlier than period")
    scope = {"portfolio": principal["portfolio"], "application": request.application,
             "period": request.period, "previous_period": request.previous_period,
             "scorecard": request.scorecard}
    return initial(request.question, scope)

@app.post("/v1/ask")
async def ask(request: Ask, principal=Depends(authorize)):
    state = input_for(request, principal)
    thread = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread}, "recursion_limit": 20}
    try:
        result = await asyncio.wait_for(app.state.graph.ainvoke(state, config), timeout=180)
        return {"thread_id": thread, **result["answer"]}
    except Exception as exc:
        log.error("QMO workflow failed: %s", type(exc).__name__)
        raise HTTPException(503, "QMO analysis unavailable; retry later") from exc

@app.get("/health")
def health():
    return {"status": "ok", "mode": os.getenv("QMO_MODE", "demo")}
