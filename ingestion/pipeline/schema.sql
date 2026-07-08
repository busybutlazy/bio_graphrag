CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    topic TEXT,
    grade_level TEXT,
    source_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id TEXT UNIQUE NOT NULL,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id),
    content TEXT NOT NULL,
    concept_ids JSONB NOT NULL DEFAULT '[]',
    topic TEXT,
    grade_level TEXT,
    source_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL,
    source_path TEXT,
    stats JSONB,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS curation_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id TEXT UNIQUE NOT NULL,
    item_type TEXT NOT NULL,
    action TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    proposed_by TEXT NOT NULL,
    reviewed_by TEXT,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS graph_change_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    change_id TEXT UNIQUE NOT NULL,
    curation_item_id UUID REFERENCES curation_items(id),
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT,
    before_state JSONB,
    after_state JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS query_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id TEXT UNIQUE NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    retrieval_debug JSONB,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id TEXT UNIQUE NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    metrics JSONB,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS evaluation_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES evaluation_runs(id),
    question_id TEXT NOT NULL,
    question TEXT NOT NULL,
    expected_nodes JSONB,
    retrieved_nodes JSONB,
    passed BOOLEAN,
    notes TEXT
);

-- Per-company access accounts for the token-spending endpoints (/query,
-- /check-answer). vendor_code is the human-readable handle used for admin and
-- for usage records; api_key is the secret sent as the X-API-Key header. These
-- are demo-grade access keys (plaintext) — fine for a portfolio demo, not a
-- production credential store.
CREATE TABLE IF NOT EXISTS vendors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_code TEXT UNIQUE NOT NULL,   -- e.g. "acme"; the manual/usage identity
    name TEXT NOT NULL,                 -- display name, e.g. "Acme Corp"
    api_key TEXT UNIQUE NOT NULL,       -- the credential (X-API-Key)
    expires_at DATE,                    -- NULL = no expiry; past = expired
    token_quota INTEGER NOT NULL,       -- cumulative token cap; 0 = no token access
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per token-spending request; tokens_used = embedding + completion.
-- Keyed by vendor_code (not the secret key) so the table stays hand-readable.
CREATE TABLE IF NOT EXISTS vendor_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_code TEXT NOT NULL,
    tokens_used INTEGER NOT NULL,
    endpoint TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS vendor_usage_code_idx ON vendor_usage (vendor_code);
