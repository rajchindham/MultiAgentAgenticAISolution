# QMO Scorecard RAG sample

A runnable FastAPI example that joins **structured metric evidence** with retrieved scorecard documentation. All rows are fictional. SQLite stores metrics and documents; optional OpenAI embeddings provide semantic retrieval. Without an API key, simple keyword retrieval and an evidence-only response keep the demo usable offline.

## Run

```bash
python -m venv .venv
source .venv/bin/activate                # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.cli seed
uvicorn app.main:app --reload
```

Ask a question:

```bash
curl -X POST http://127.0.0.1:8000/ask -H 'Content-Type: application/json' \
  -d '{"question":"What is the Mobile App current release defect count and what does zero mean?","application":"Mobile App","period":"2026-08","scorecard":"product_quality"}'
```

For semantic retrieval and generated cited answers, set `OPENAI_API_KEY`, run `python -m app.cli index`, then restart the API. The key remains server side. Models can be set with `QMO_CHAT_MODEL` and `QMO_EMBED_MODEL`. Run `pytest -q` to check the sample data rules.

## Flow

1. `/ask` validates optional portfolio, application, period, and scorecard filters.
2. A parameterized fixed-column query loads at most 100 matching metrics.
3. Documentation is retrieved within the selected scorecard scope, by embedding cosine similarity if indexed, or keyword overlap otherwise.
4. The model receives only retrieved evidence and cites `[M#]` metric rows and `[D#]` documents. The API also returns full source records so the UI can render links or evidence cards.

## Connect to your QMO environment

Replace the seed data and `metrics()` in `app/core.py` with a read-only repository querying approved views such as `digital_qmo_maturity_summary_view` and `product_quality_summary_vw_v3`, or the underlying `Digital_QMO_KPI_Metrics`. Map each result to the fields in the current response. Ingest your approved metric definitions, threshold rules, and refresh metadata into `documents`; re-index embeddings after changes. Do not infer threshold colors from numeric values: use the configured `dbo_dev.digital_color_threshold` or validated dashboard output. `scorecard_data_refreshdate()` can supply refresh timestamps. Implement portfolio/application row authorization at the data query and document retrieval layers before exposing production data. Add pagination or aggregates for broad questions; the 100-row limit makes broad portfolio answers incomplete. Validate generated statements against source citations before displaying high-impact recommendations.

This sample does not claim to connect to your actual SQL Server, authenticate users, or contain real QMO data. For a deployed app, add identity validation, RBAC, query logging with sensitive data handling, index update jobs, and monitoring.
