import operator
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from qmo.rules import metric_facts, compare_periods, validation_errors

class State(TypedDict, total=False):
    question: str
    scope: dict
    plan: dict
    evidence: Annotated[list[dict], operator.add]
    trace: Annotated[list[str], operator.add]
    limitations: Annotated[list[str], operator.add]
    findings: list[dict]
    draft: dict
    repairs: int
    errors: list[str]
    answer: dict

# Every specialist is itself a LangGraph subgraph. Tool execution is model-driven
# in OpenAI mode; demo mode deterministically calls the same bounded tools.
class SpecialistState(TypedDict):
    snapshot: dict
    update: dict

def specialist(name, handler):
    async def execute(local):
        return {"update": await handler(local["snapshot"])}
    graph = StateGraph(SpecialistState)
    graph.add_node(name, execute)
    graph.add_edge(START, name)
    graph.add_edge(name, END)
    compiled = graph.compile()
    async def invoke(state):
        result = await compiled.ainvoke({"snapshot": state, "update": {}})
        return result["update"]
    return invoke


def build_graph(model, repo, checkpointer=None):
    async def supervisor(state):
        plan = await model.plan(state)
        # Prevent the planner from skipping essential live metrics for questions
        # other than explicit definition-only requests.
        if not state["question"].lower().startswith(("define", "what is")):
            plan.need_metrics = True
        if state["scope"].get("previous_period"):
            plan.need_metrics = True
            plan.need_trends = True
        return {"plan": plan.model_dump(), "trace": ["supervisor:delegate"]}

    async def metrics_agent(state):
        result = []
        if state["plan"]["need_metrics"]:
            async def current():
                rows = await repo.metrics(state["scope"])
                result.extend(rows)
                return rows
            tools = {"get_current_metrics": ("Read current QMO KPI values, status and refresh date.", current)}
            if state["plan"]["need_trends"] and state["scope"].get("previous_period"):
                async def baseline():
                    rows = await repo.metrics(state["scope"], state["scope"]["previous_period"])
                    result.extend(rows)
                    return rows
                tools["get_baseline_metrics"] = ("Read previous reporting period for comparison.", baseline)
            await model.use_tools("Metric specialist: call the available read-only metric tools.",
                                  state["question"], tools)
        return {"evidence": result, "trace": ["metrics_agent:complete"],
            "limitations": ["No current metric evidence."] if state["plan"]["need_metrics"] and
                not any(e["payload"]["period"] == state["scope"]["period"] for e in result) else []}

    async def dashboard_rag_agent(state):
        result = []
        if state["plan"]["need_documents"]:
            async def retrieve():
                docs = await repo.documents(state["plan"]["query"][:1500], state["scope"])
                result.extend(docs)
                return docs
            await model.use_tools("Dashboard RAG agent: retrieve KPI definitions using the existing QMO RAG code.",
                state["question"], {"search_scorecard_documents":
                ("Search original Dashboard RAG documentation within the authorized scorecard.", retrieve)})
        return {"evidence": result, "trace": ["dashboard_rag_agent:complete"],
            "limitations": ["No matching documentation."] if state["plan"]["need_documents"] and not result else []}

    async def analyst(state):
        findings, limitations = [], []
        async def calculate():
            findings.extend(metric_facts(state["evidence"]))
            trends, issues = compare_periods(state["evidence"], state["scope"])
            findings.extend(trends)
            limitations.extend(issues)
            return {"findings": findings, "limitations": limitations}
        await model.use_tools("Trend analysis specialist: calculate facts with the deterministic analysis tool.",
            state["question"], {"analyze_scorecard_evidence":
            ("Apply zero/null rules and compare available reporting periods without inventing thresholds.", calculate)})
        return {"findings": findings, "limitations": limitations, "trace": ["analysis_agent:complete"]}

    async def recommendation(state):
        report = await model.report(state)
        return {"draft": report.model_dump(), "trace": ["recommendation_agent:complete"]}

    async def validate(state):
        from qmo.models import Report
        errors = validation_errors(Report.model_validate(state["draft"]), state["evidence"])
        return {"errors": errors, "repairs": state.get("repairs", 0) + int(bool(errors)),
                "trace": ["validator:" + ("blocked" if errors else "passed")]}

    async def finish(state):
        current_metrics = [e for e in state["evidence"] if e["kind"] == "metric" and
                           e["payload"]["period"] == state["scope"]["period"]]
        enough = (not state["plan"]["need_metrics"] or bool(current_metrics)) and (
                 not state["plan"]["need_documents"] or any(e["kind"] == "document" for e in state["evidence"]))
        draft = state["draft"] if not state["errors"] else {
            "observations": [], "recommendations": [],
            "limitations": ["Generated prose failed evidence validation and was withheld."]}
        return {"answer": {"status": "ok" if enough and not state["errors"] else "insufficient_evidence",
            "scope": state["scope"], "findings": state["findings"], **draft,
            "limitations": list(dict.fromkeys(state["limitations"] + draft["limitations"])),
            "sources": state["evidence"], "trace": state["trace"] + ["response:complete"]}}

    graph = StateGraph(State)
    graph.add_node("supervisor", supervisor)
    graph.add_node("metrics_agent", specialist("metrics", metrics_agent))
    graph.add_node("dashboard_rag_agent", specialist("rag", dashboard_rag_agent))
    graph.add_node("analysis_agent", specialist("analysis", analyst))
    graph.add_node("recommendation_agent", specialist("recommendation", recommendation))
    graph.add_node("validate", validate)
    graph.add_node("finish", finish)
    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "metrics_agent")
    graph.add_edge("supervisor", "dashboard_rag_agent")
    # Barrier: analysis starts only after both retrieval agents complete.
    graph.add_edge(["metrics_agent", "dashboard_rag_agent"], "analysis_agent")
    graph.add_edge("analysis_agent", "recommendation_agent")
    graph.add_edge("recommendation_agent", "validate")
    graph.add_conditional_edges("validate", lambda s: "repair" if s["errors"] and s["repairs"] < 2 else "finish",
                                {"repair": "recommendation_agent", "finish": "finish"})
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def initial(question, scope):
    return {"question": question, "scope": scope, "evidence": [], "trace": [],
            "limitations": [], "findings": [], "repairs": 0, "errors": []}
