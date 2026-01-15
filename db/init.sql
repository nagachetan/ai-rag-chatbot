-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Create app user safely
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT FROM pg_roles WHERE rolname = 'rag_user'
  ) THEN
    CREATE USER rag_user WITH PASSWORD 'rag_pass';
  END IF;
END
$$;

-- Create documents table as superuser
CREATE TABLE IF NOT EXISTS public.documents (
    id SERIAL PRIMARY KEY,
    repo_name TEXT UNIQUE,
    content TEXT,
    embedding VECTOR(768)
);

-- -------------------------------
-- Permissions
-- -------------------------------
GRANT CONNECT ON DATABASE postgres TO rag_user;
GRANT USAGE ON SCHEMA public TO rag_user;

-- Table access (current table)
GRANT ALL PRIVILEGES ON public.documents TO rag_user;

-- Sequence access (current sequences)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rag_user;

-- -------------------------------
-- Default privileges (FUTURE)
-- -------------------------------

-- Future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL ON TABLES TO rag_user;

-- ✅ Future sequences (THIS WAS THE MISSING PIECE)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT ON SEQUENCES TO rag_user;

-- -------------------------------
-- Safety limit
-- -------------------------------
ALTER USER rag_user CONNECTION LIMIT 5;

