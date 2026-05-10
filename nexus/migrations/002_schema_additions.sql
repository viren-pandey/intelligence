-- Schema additions for v2.0: speed, webhooks, rate limiting, crawler sources

ALTER TABLE api_clients ADD COLUMN IF NOT EXISTS webhook_url TEXT;
ALTER TABLE api_clients ADD COLUMN IF NOT EXISTS webhook_events JSONB DEFAULT '[]';
ALTER TABLE api_clients ADD COLUMN IF NOT EXISTS rate_limit_per_hour INTEGER DEFAULT 100;
ALTER TABLE api_clients ADD COLUMN IF NOT EXISTS max_results_cap INTEGER DEFAULT 50;
ALTER TABLE api_clients ADD COLUMN IF NOT EXISTS credits_remaining INTEGER DEFAULT 0;
ALTER TABLE api_clients ADD COLUMN IF NOT EXISTS contact_email TEXT;
ALTER TABLE api_clients ADD COLUMN IF NOT EXISTS password_hash TEXT;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS report_count INTEGER DEFAULT 0;

ALTER TABLE crawl_source_logs ADD COLUMN IF NOT EXISTS avg_latency_ms INTEGER DEFAULT 0;
ALTER TABLE crawl_source_logs ADD COLUMN IF NOT EXISTS using_playwright BOOLEAN DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS crawler_sources (
    source_name TEXT PRIMARY KEY,
    enabled BOOLEAN DEFAULT TRUE,
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    failure_count_24h INTEGER DEFAULT 0,
    success_count_24h INTEGER DEFAULT 0,
    avg_jobs_per_crawl FLOAT DEFAULT 0,
    avg_latency_ms INTEGER DEFAULT 0,
    notes TEXT,
    requires_js BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id TEXT,
    client_id UUID REFERENCES api_clients(id),
    webhook_url TEXT,
    event_type TEXT,
    payload_size_bytes INTEGER DEFAULT 0,
    http_status INTEGER,
    delivered_at TIMESTAMPTZ DEFAULT NOW(),
    retry_count INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS contact_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES api_clients(id),
    client_name TEXT,
    contact_email TEXT,
    subject TEXT,
    message TEXT,
    request_type TEXT DEFAULT 'credit_increase',
    new_limit_requested INTEGER,
    status TEXT DEFAULT 'pending',
    admin_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS rate_limit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES api_clients(id),
    endpoint TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO crawler_sources (source_name, enabled, requires_js) VALUES
    ('remoteok', TRUE, FALSE),
    ('yc_jobs', TRUE, FALSE),
    ('weworkremotely', TRUE, FALSE),
    ('linkedin_public', TRUE, TRUE),
    ('github_hiring', TRUE, FALSE),
    ('google_serp', TRUE, TRUE),
    ('niche_boards', TRUE, FALSE),
    ('career_pages', TRUE, FALSE),
    ('internshala_public', TRUE, FALSE),
    ('founder_posts', TRUE, FALSE),
    ('producthunt', TRUE, FALSE),
    ('nitter_twitter', TRUE, FALSE),
    ('discord_jobs', TRUE, TRUE)
ON CONFLICT (source_name) DO NOTHING;

UPDATE api_clients SET credits_remaining = 50, rate_limit_per_hour = 50, max_results_cap = 10 WHERE client_name = 'internhunt';
INSERT INTO api_clients (client_name, api_key, credits_remaining, rate_limit_per_hour, max_results_cap, contact_email)
VALUES ('demo', 'nexus-demo-key', 5, 5, 5, 'demo@example.com')
ON CONFLICT (api_key) DO NOTHING;

INSERT INTO api_clients (client_name, api_key, credits_remaining, rate_limit_per_hour, max_results_cap, contact_email)
VALUES ('admin', 'nexus-admin-dev', 999999, 999999, 999, 'admin@nexus.local')
ON CONFLICT (api_key) DO NOTHING;
