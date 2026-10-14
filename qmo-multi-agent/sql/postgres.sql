CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS qmo_chunks (
  id text PRIMARY KEY,
  portfolio text NOT NULL,
  application text NOT NULL,
  scorecard text NOT NULL CHECK (scorecard IN ('maturity','product_quality')),
  title text NOT NULL,
  content text NOT NULL,
  source text NOT NULL,
  version text NOT NULL,
  embedding_model text NOT NULL,
  embedding vector(1536) NOT NULL,
  active boolean NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS qmo_chunks_scope
  ON qmo_chunks(portfolio, application, scorecard, embedding_model) WHERE active;
-- Exact vector search for this starter. Benchmark scoped HNSW/IVFFlat when scaling.
