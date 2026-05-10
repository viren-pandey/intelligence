ALTER TABLE api_clients ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE contact_requests ADD COLUMN IF NOT EXISTS request_type TEXT DEFAULT 'user_message';
