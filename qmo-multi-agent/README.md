# QMO Scorecard Multi-Agent AI

A runnable Python/FastAPI reference implementation using LangGraph and OpenAI.
It incorporates the actual earlier `qmo-scorecard-rag-codebase.zip` source and data.

| Agent | Role | Tools/output |
|---|---|---|
| Supervisor | Plan the investigation | Pydantic Plan through OpenAI |
| Metrics specialist | Retrieve authoritative KPI records | get_current_metrics, get_baseline_metrics |
| Dashboard RAG specialist | Reuse the original QMO retrieval code | search_scorecard_documents → core.retrieve |
| Trend analysis specialist | Calculate facts with deterministic Python | analyze_scorecard_evidence |
| Recommendation specialist | Draft observations and suggestions with references | Pydantic Report through OpenAI |

The validator is a deterministic control node. It checks retrieved evidence IDs,
blocks numeric model prose, and permits one repair attempt before withholding invalid
prose. Numeric metrics remain available in the authoritative findings field.

```mermaid
flowchart TD
  S["Supervisor agent"] --> M["Metrics agent"]
  S --> R["Dashboard RAG agent"]
  M --> A["Analysis agent"]
  R --> A
  A --> N["Recommendation agent"]
  N --> V["Evidence validator"]
  V -->|"one repair"| N
  V -->|"valid or withheld"| F["Response with sources"]
```

Retrieval agents run in parallel; a join barrier waits for both. Each specialist
uses its own LangGraph subgraph and returns only partial updates. Reducers combine
concurrent evidence/trace updates. In OpenAI mode the model selects native function
calls within bounded loops. Offline mode executes the same tools deterministically.

## Run offline

Python 3.12 was tested. From this directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m qmo.demo
python -m pytest -q
```

Windows activation: `.venv\Scripts\activate`.
The original sample has Mobile App and Web Check-in data for 2026-08, with no baseline
month. The demo reports missing comparison evidence rather than inventing a decline.
All sample KPI values are illustrative. See docs/demo-output.json and
 docs/verification.txt for verified results.

## FastAPI

Copy `.env.example` to `.env`; set a private QMO_API_TOKEN. Start:

```bash
uvicorn qmo.main:app --host 127.0.0.1 --port 8000
```

Swagger: http://127.0.0.1:8000/docs

```bash
curl http://127.0.0.1:8000/v1/ask \
  -H "Authorization: Bearer YOUR_CONFIGURED_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"Explain Current Release Defects and Functional Automation Failure Rate", "application":"Mobile App", "period":"2026-08", "previous_period":"2026-07", "scorecard":"product_quality"}'
```

Response: thread_id, status, scope, findings, observations, recommendations,
limitations, sources and trace. Findings contain exact values, units, periods,
refresh dates, statuses and evidence IDs. Scorecards: maturity or product_quality.

## OpenAI mode

Set in `.env` and restart:

```dotenv
QMO_MODE=openai
OPENAI_API_KEY=your-key
QMO_MODEL=gpt-4.1-mini
QMO_DATA_BACKEND=sample
```

The default retains the earlier RAG project's model choice. Configure a model
available to your account supporting native function calling and structured outputs.
The OpenAI provider uses Responses API parse/create, Pydantic schemas, store=False,
request timeouts, SDK retries, refusal/incomplete checks and bounded tool rounds.
Live OpenAI requests were not made during verification.

The original RAG uses lexical retrieval until its SQLite documents have embeddings:

```bash
python -c 'from dotenv import load_dotenv; load_dotenv(); from qmo.legacy_rag.core import init_db,index_embeddings; init_db(); print(index_embeddings())'
```

## Original Dashboard RAG integration

qmo/legacy_rag/core.py was copied from the original archive along with its actual
scorecard_docs.json. Changes: document path relocated within the package; offline
mode explicitly bypasses query embeddings. Original README is retained alongside it.

DashboardRAGRepository.metrics calls original core.metrics; documents calls original
core.retrieve. The Dashboard RAG specialist invokes retrieval through an agent tool.
Original core.answer is retained behind original_answer for UI compatibility, but
is not treated as verified evidence. Final prose comes from the recommendation
agent, avoiding a second generation pass inside the RAG specialist.

## SQL Server and pgvector

Model provider and data backend are separate. OpenAI mode with sample still reads
SQLite sample data, not a production database.

1. Install requirements-enterprise.txt and a Microsoft SQL Server ODBC driver.
2. Map your actual SQL Server columns to the view in docs/SQLSERVER_CONTRACT.md.
3. Apply sql/postgres.sql in a PostgreSQL database with pgvector installed.
4. Set QMO_DATA_BACKEND=enterprise and both database DSNs in .env.
5. Set QMO_INDEX_PORTFOLIO and QMO_INDEX_APPLICATION; run python -m qmo.index.
   The included indexer loads the original sample docs; replace the input with your
   approved enterprise documentation for actual deployment.

Enterprise adapters use parameterized SQL, portfolio/application/scorecard filters,
period filters, active document and embedding-model filters, top-k and timeouts.
Embeddings are 1536-dimensional; changing models requires compatible dimensions and
reindexing. Calibrate the sample similarity cutoff with labeled retrieval cases.
Actual enterprise connectivity and physical column mapping were not tested here.

## Rules and production boundaries

Missing values remain None/No Data. Measured zero Current Release Defects and zero
Functional Automation Failure Rate are Green. Other statuses are preserved from the
governed source. Trends require two non-null periods and matching units; percent
changes are expressed in percentage points. There are no invented thresholds,
weights, or causal explanations. Apply the special missing-failure-rate/count rule
in your approved merged view while retaining raw missing-value lineage. Weighted
score contributor analysis requires governed weights and is not fabricated here.

The API's configured bearer token and application allow-list are for service-level
scoping and local testing. Replace them with enterprise OAuth2/JWT validation and
user-specific permissions. Tool function arguments cannot alter the bound scope.

InMemorySaver is process-local, lost on restart. Inject a durable checkpointer through
build_graph(..., checkpointer=...) for production. No state-read/resume endpoints or
operational write tools are exposed. No Jira tickets, emails or metric writes occur;
authenticated human approval and idempotency must be added before enabling actions.

Schema and evidence-ID checks do not prove semantic entailment. Evaluate groundedness
and review prose before operational decisions. Add enterprise identity, DB pooling,
load testing, request usage telemetry, token budgets, freshness policies and durable
checkpoints for production. Row/top-k limits bound retrieval but are not a complete
token budget. This is a tested reference implementation, not a deployed integration.

## Main files

- qmo/graph.py: supervisor, specialist subgraphs, join and validation loop
- qmo/model.py: native OpenAI tools and structured outputs; offline provider
- qmo/repository.py: original RAG and SQL Server/pgvector adapters
- qmo/rules.py: deterministic calculations and evidence-reference checks
- qmo/main.py: authenticated API and scope enforcement
- qmo/index.py: scoped pgvector indexing
- tests/test_solution.py: nine tests for integration, rules, API and dispatch

Official references:
https://docs.langchain.com/oss/python/langgraph/graph-api
https://developers.openai.com/api/docs/guides/structured-outputs
