CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES api_clients(id),
    title TEXT DEFAULT 'New message from admin',
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS notifications_client_idx ON notifications (client_id);
CREATE INDEX IF NOT EXISTS notifications_unread_idx ON notifications (client_id, is_read);
