import asyncio
import json
import uuid
from qmo.legacy_rag.core import init_db
from qmo.model import DemoModel
from qmo.repository import DashboardRAGRepository
from qmo.graph import build_graph, initial

async def main():
    init_db()
    graph = build_graph(DemoModel(), DashboardRAGRepository())
    state = initial("Explain Current Release Defects and Functional Automation Failure Rate.",
        {"portfolio": "Digital Platforms", "application": "Mobile App", "period": "2026-08",
         "previous_period": "2026-07", "scorecard": "product_quality"})
    result = await graph.ainvoke(state, {"configurable": {"thread_id": str(uuid.uuid4())}})
    print(json.dumps(result["answer"], indent=2))

if __name__ == "__main__":
    asyncio.run(main())
