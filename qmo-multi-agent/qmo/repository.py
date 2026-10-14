"""Adapter around the actual QMO Dashboard RAG core included in this project."""
import asyncio
from qmo.legacy_rag import core

class DashboardRAGRepository:
    async def metrics(self, scope, period=None):
        rows = await asyncio.to_thread(core.metrics, scope["portfolio"],
            scope["application"], period or scope["period"], scope["scorecard"])
        return [{"id": "metric:" + ":".join(str(r[k]) for k in
                 ("application", "period", "scorecard", "metric")),
                 "kind": "metric", "source": "original-rag/sqlite/metrics",
                 "payload": r} for r in rows]

    async def documents(self, query, scope):
        docs = await asyncio.to_thread(core.retrieve, query, scope["scorecard"], 3)
        return [{"id": "doc:" + d["id"], "kind": "document",
                 "source": "original-rag/scorecard_docs.json", "payload": d} for d in docs]

    async def original_answer(self, question, metrics, documents):
        # Compatibility hook for an existing /ask UI. Not used as authoritative evidence
        # because the original answer() does not perform a grounding validation step.
        return await asyncio.to_thread(core.answer, question,
            [m["payload"] for m in metrics], [d["payload"] for d in documents])


class EnterpriseRepository:
    """SQL Server and pgvector adapters; queries use a documented contract view.

    Replace the contract view mapping with your approved QMO physical columns.
    The same Dashboard RAG agent uses this adapter when enterprise mode is set.
    """
    def __init__(self, client):
        import os
        self.client = client
        self.sqlserver = os.environ["QMO_SQLSERVER_DSN"]
        self.postgres = os.environ["QMO_POSTGRES_DSN"]
        if not self.sqlserver or not self.postgres:
            raise RuntimeError("Enterprise database DSNs are required")
        self.embedding_model = os.getenv("QMO_EMBED_MODEL", "text-embedding-3-small")
        self.min_similarity = float(os.getenv("QMO_MIN_SIMILARITY", "0.35"))

    async def metrics(self, scope, period=None):
        target = period or scope["period"]
        def query():
            import pyodbc
            with pyodbc.connect(self.sqlserver, timeout=5) as conn:
                cur = conn.cursor()
                cur.timeout = 10
                cur.execute("""SELECT TOP (100) portfolio, application, period,
                    scorecard, metric, value, unit, status, refreshed_at
                    FROM dbo.qmo_agent_metrics_vw
                    WHERE portfolio=? AND application=? AND period=? AND scorecard=?
                    ORDER BY metric""", scope["portfolio"], scope["application"],
                    target, scope["scorecard"])
                keys = [d[0] for d in cur.description]
                rows = [dict(zip(keys, row)) for row in cur.fetchall()]
            for r in rows:
                r["value"] = None if r["value"] is None else float(r["value"])
                r["refreshed_at"] = r["refreshed_at"].isoformat()
            return [{"id": "metric:" + ":".join(str(r[k]) for k in
                ("application", "period", "scorecard", "metric")),
                "kind": "metric", "source": "QMOMetrics_Dashboard_PROD/dbo.qmo_agent_metrics_vw",
                "payload": r} for r in rows]
        return await asyncio.to_thread(query)

    async def documents(self, query, scope):
        import asyncpg
        import json
        embedding = await self.client.embeddings.create(
            model=self.embedding_model, input=query, dimensions=1536)
        vector = json.dumps(embedding.data[0].embedding)
        conn = await asyncpg.connect(self.postgres, timeout=5)
        try:
            rows = await conn.fetch("""SELECT id, title, scorecard AS scope, content AS text,
                source, version, 1-(embedding <=> $1::vector) AS similarity
                FROM qmo_chunks WHERE portfolio=$2 AND application=$3 AND scorecard=$4
                AND embedding_model=$5 AND active=true
                ORDER BY embedding <=> $1::vector LIMIT 5""", vector,
                scope["portfolio"], scope["application"], scope["scorecard"],
                self.embedding_model, timeout=10)
            return [{"id": "doc:" + str(r["id"]), "kind": "document", "source": r["source"],
                     "payload": dict(r)} for r in rows if r["similarity"] >= self.min_similarity]
        finally:
            await conn.close()
