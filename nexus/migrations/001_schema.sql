CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

CREATE TABLE jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    company_domain TEXT,
    company_about TEXT,
    industry TEXT,
    company_size TEXT,
    funding_stage TEXT,
    location TEXT,
    remote_status TEXT CHECK (remote_status IN ('remote', 'hybrid', 'onsite', 'unknown')),
    job_type TEXT CHECK (job_type IN ('internship', 'fulltime', 'contract', 'parttime', 'unknown')),
    paid BOOLEAN DEFAULT NULL,
    stipend_inr INTEGER,
    salary_range TEXT,
    duration TEXT,
    skills_required JSONB DEFAULT '[]',
    description TEXT,
    eligibility TEXT,
    batch_eligible TEXT,
    apply_link TEXT NOT NULL,
    source_platform TEXT NOT NULL,
    source_url TEXT NOT NULL,
    posted_date TIMESTAMPTZ,
    deadline TIMESTAMPTZ,
    trust_score FLOAT DEFAULT 0.0,
    freshness_score FLOAT DEFAULT 0.0,
    niche_score FLOAT DEFAULT 0.0,
    is_niche BOOLEAN DEFAULT FALSE,
    verified BOOLEAN DEFAULT FALSE,
    is_expired BOOLEAN DEFAULT FALSE,
    simhash BIGINT,
    crawl_session_id UUID,
    recruiter_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX jobs_company_idx ON jobs (company);
CREATE INDEX jobs_source_idx ON jobs (source_platform);
CREATE INDEX jobs_deadline_idx ON jobs (deadline) WHERE is_expired = FALSE;
CREATE INDEX jobs_skills_gin ON jobs USING GIN (skills_required);
CREATE INDEX jobs_simhash_idx ON jobs (simhash);
CREATE INDEX jobs_trust_idx ON jobs (trust_score);

CREATE TABLE crawl_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    triggered_by TEXT NOT NULL,
    source_system TEXT DEFAULT 'internhunt',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    total_sources INTEGER DEFAULT 0,
    sources_succeeded INTEGER DEFAULT 0,
    sources_failed INTEGER DEFAULT 0,
    total_jobs_found INTEGER DEFAULT 0,
    total_jobs_saved INTEGER DEFAULT 0,
    duplicates_removed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running' CHECK (status IN ('running', 'complete', 'partial', 'failed'))
);

CREATE TABLE crawl_source_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES crawl_sessions(session_id),
    source_name TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    pages_crawled INTEGER DEFAULT 0,
    jobs_found INTEGER DEFAULT 0,
    jobs_rejected INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    error_messages JSONB DEFAULT '[]',
    status TEXT DEFAULT 'running'
);

CREATE TABLE deleted_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL,
    title TEXT,
    company TEXT,
    location TEXT,
    remote_status TEXT,
    job_type TEXT,
    paid BOOLEAN,
    stipend_inr INTEGER,
    skills_required JSONB DEFAULT '[]',
    apply_link TEXT,
    source_platform TEXT,
    posted_date TIMESTAMPTZ,
    original_deadline TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_reason TEXT CHECK (deleted_reason IN ('deadline_passed', 'manual', 'trust_fail', 'link_dead', 'duplicate'))
);

CREATE INDEX deleted_jobs_deleted_at_idx ON deleted_jobs (deleted_at DESC);
CREATE INDEX deleted_jobs_reason_idx ON deleted_jobs (deleted_reason);

CREATE TABLE recruiter_intelligence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_domain TEXT NOT NULL,
    recruiter_name TEXT,
    recruiter_email TEXT,
    recruiter_phone TEXT,
    recruiter_linkedin TEXT,
    hr_name TEXT,
    hr_email TEXT,
    source_url TEXT,
    email_verified BOOLEAN DEFAULT FALSE,
    extracted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX recruiter_domain_email_idx ON recruiter_intelligence (company_domain, recruiter_email)
    WHERE recruiter_email IS NOT NULL;

CREATE TABLE company_intelligence (
    company_domain TEXT PRIMARY KEY,
    company_name TEXT,
    company_size TEXT,
    industry TEXT,
    funding_stage TEXT,
    founded_year INTEGER,
    headquarters TEXT,
    tech_stack JSONB DEFAULT '[]',
    mca_registered BOOLEAN,
    domain_age_days INTEGER,
    last_refreshed TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE api_clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_name TEXT NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);

CREATE TABLE analyze_requests (
    request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_client_id UUID REFERENCES api_clients(id),
    user_id_from_client TEXT,
    crawl_session_id UUID REFERENCES crawl_sessions(session_id),
    status TEXT DEFAULT 'pending',
    results_count INTEGER DEFAULT 0,
    processing_time_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

INSERT INTO api_clients (client_name, api_key) VALUES ('internhunt', 'nexus-client-dev');
