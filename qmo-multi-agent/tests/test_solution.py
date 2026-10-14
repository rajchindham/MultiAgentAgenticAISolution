import asyncio
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from qmo.models import Report, Claim
from qmo.model import DemoModel, OpenAIModel
from qmo.graph import build_graph, initial
from qmo.rules import metric_facts, compare_periods, validation_errors
from qmo.repository import DashboardRAGRepository
from qmo.legacy_rag import core

SCOPE = {"portfolio": "Digital Platforms", "application": "Mobile App",
         "period": "2026-08", "previous_period": "2026-07", "scorecard": "product_quality"}

def run(graph, scope=None):
    return asyncio.run(graph.ainvoke(initial("Explain Current Release Defects", scope or SCOPE),
        {"configurable": {"thread_id": "test"}}))["answer"]

@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("QMO_MODE", "demo")
    monkeypatch.setattr(core, "DB_PATH", tmp_path / "qmo.db")
    core.init_db()
    return DashboardRAGRepository()

def test_original_rag_integrated_and_parallel_join(repo):
    answer = run(build_graph(DemoModel(), repo))
    assert answer["status"] == "ok"
    assert any(e["id"] == "doc:quality-guide" for e in answer["sources"])
    assert answer["trace"].count("analysis_agent:complete") == 1
    assert answer["trace"].index("analysis_agent:complete") > answer["trace"].index("dashboard_rag_agent:complete")
    assert not any(f["type"] == "trend" for f in answer["findings"])
    assert any("baseline" in x for x in answer["limitations"])

def test_zero_is_green_null_is_no_data(repo):
    e = asyncio.run(repo.metrics(SCOPE))
    assert next(x for x in metric_facts(e) if x["metric"] == "Current Release Defects")["status"] == "Green"
    scope = {**SCOPE, "application": "Web Check-in", "scorecard": "maturity"}
    facts = metric_facts(asyncio.run(repo.metrics(scope)))
    assert facts[0]["value"] is None and facts[0]["status"] == "No Data"

def test_unknown_app_not_fabricated(repo):
    answer = run(build_graph(DemoModel(), repo), {**SCOPE, "application": "UNKNOWN"})
    assert answer["status"] == "insufficient_evidence"
    assert not answer["findings"]

def test_real_comparison_uses_percentage_points(repo):
    with core.connect() as db:
        db.execute("""INSERT INTO metrics(portfolio,application,period,scorecard,metric,value,unit,status,refreshed_at)
          VALUES(?,?,?,?,?,?,?,?,?)""", ("Digital Platforms", "Mobile App", "2026-07", "product_quality",
          "Functional Automation Failure Rate", 4.5, "percent", "Amber", "2026-08-01T08:00:00Z"))
    answer = run(build_graph(DemoModel(), repo))
    trend = next(f for f in answer["findings"] if f["type"] == "trend")
    assert trend["delta"] == -2.0 and trend["delta_unit"] == "percentage points"
    assert len(trend["evidence_ids"]) == 2

def test_unretrieved_citations_rejected():
    report = Report(observations=[Claim(text="Unsupported", evidence_ids=["fake"])], recommendations=[], limitations=[])
    assert validation_errors(report, [])

class BadModel(DemoModel):
    async def report(self, state):
        return Report(observations=[Claim(text="Invented", evidence_ids=["fake"])], recommendations=[], limitations=[])

def test_failed_validation_bounded_and_prose_withheld(repo):
    answer = run(build_graph(BadModel(), repo))
    assert answer["status"] == "insufficient_evidence"
    assert answer["observations"] == []
    assert answer["trace"].count("validator:blocked") == 2
    assert answer["findings"]

def test_api_auth_scope_and_period(repo, monkeypatch):
    monkeypatch.setenv("QMO_API_TOKEN", "test-token")
    from qmo.main import app
    request = {"question": "Explain Current Release Defects", "application": "Mobile App",
               "period": "2026-08", "scorecard": "product_quality"}
    with TestClient(app) as client:
        assert client.post("/v1/ask", json=request).status_code == 401
        headers = {"Authorization": "Bearer test-token"}
        assert client.post("/v1/ask", headers=headers, json={**request, "application": "Unknown"}).status_code == 403
        assert client.post("/v1/ask", headers=headers, json={**request, "period": "2026-13"}).status_code == 422
        assert client.post("/v1/ask", headers=headers, json={**request, "previous_period": "2026-09"}).status_code == 422
        response = client.post("/v1/ask", headers=headers, json=request)
        assert response.status_code == 200 and response.json()["status"] == "ok"

def test_native_openai_tool_dispatch_without_network():
    model = object.__new__(OpenAIModel)
    model.model = "test-model"
    seen = []
    async def create(**kwargs):
        name = kwargs["tools"][0]["name"]
        return NS(status="completed", output=[NS(type="function_call", name=name, arguments="{}", call_id="c1")])
    async def tool():
        seen.append("called")
        return []
    model.client = NS(responses=NS(create=create))
    asyncio.run(model.use_tools("test", "question", {"read_metrics": ("read", tool)}))
    assert seen == ["called"]

def test_malicious_tool_scope_args_rejected():
    model = object.__new__(OpenAIModel)
    model.model = "test-model"
    async def create(**kwargs):
        return NS(status="completed", output=[NS(type="function_call", name="read",
            arguments='{"application":"secret"}', call_id="c1")])
    async def tool():
        pytest.fail("Rejected tool must not execute")
    model.client = NS(responses=NS(create=create))
    with pytest.raises(ValueError):
        asyncio.run(model.use_tools("test", "question", {"read": ("read", tool)}))
