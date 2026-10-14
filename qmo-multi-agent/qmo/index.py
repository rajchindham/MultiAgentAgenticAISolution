"""Index the original RAG sample documents into the enterprise pgvector schema."""
import asyncio
import json
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from qmo.legacy_rag.core import DOCS_PATH

async def main():
    import asyncpg
    load_dotenv()
    # Required explicit scope: do not copy a document into every user's application.
    portfolio = os.environ["QMO_INDEX_PORTFOLIO"]
    application = os.environ["QMO_INDEX_APPLICATION"]
    conn = await asyncpg.connect(os.environ["QMO_POSTGRES_DSN"])
    model = os.getenv("QMO_EMBED_MODEL", "text-embedding-3-small")
    try:
        async with AsyncOpenAI(timeout=25, max_retries=2) as client:
            for doc in json.loads(DOCS_PATH.read_text()):
                response = await client.embeddings.create(model=model, dimensions=1536,
                    input=doc["title"] + " " + doc["text"])
                identifier = json.dumps([portfolio, application, doc["id"]])
                await conn.execute("""INSERT INTO qmo_chunks
                    (id,portfolio,application,scorecard,title,content,source,version,embedding_model,embedding)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::vector)
                    ON CONFLICT(id) DO UPDATE SET content=EXCLUDED.content,
                    title=EXCLUDED.title, version=EXCLUDED.version,
                    embedding_model=EXCLUDED.embedding_model,embedding=EXCLUDED.embedding,active=true""",
                    identifier, portfolio, application, doc["scope"], doc["title"], doc["text"],
                    "original-rag/scorecard_docs.json", "1", model,
                    json.dumps(response.data[0].embedding))
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
