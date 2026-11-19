-- Idempotent. Applied by scripts/ingest.py, or paste into Supabase SQL editor.
create extension if not exists vector;

create table if not exists chunks (
    chunk_id  text primary key,
    doc       text not null,
    heading   text not null,
    text      text not null,
    tiers     text[] not null,
    embedding vector(768) not null
);

create index if not exists chunks_embedding_hnsw
    on chunks using hnsw (embedding vector_cosine_ops);

-- Block Supabase's public REST API from reading this table. The backend connects
-- as the postgres role, which bypasses RLS.
alter table chunks enable row level security;
