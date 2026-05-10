-- Remove duplicate api_clients by client_name, keeping the oldest (lowest id)
DELETE FROM api_clients a USING api_clients b
WHERE a.client_name = b.client_name
  AND a.id > b.id;

-- Add UNIQUE constraint on client_name (safe: idempotent via DO block)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'api_clients_client_name_key'
      AND conrelid = 'api_clients'::regclass
  ) THEN
    ALTER TABLE api_clients ADD CONSTRAINT api_clients_client_name_key UNIQUE (client_name);
  END IF;
END $$;
