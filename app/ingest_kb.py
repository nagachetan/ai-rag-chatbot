#!/usr/bin/env python3
"""
ingest_kb.py
-------------
Bulk ingestion script for pgvector RAG system.

- Ensures pgvector schema exists
- Reads files from a directory
- Chunks content
- Generates embeddings via Ollama
- Upserts into pgvector
"""

import os
import json
import logging
import requests
import psycopg2
from pathlib import Path
from typing import List

# -------------------- LOGGING --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# -------------------- CONFIG --------------------
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")

PGVECTOR_CONN = {
    "dbname": os.getenv("PG_DB", "postgres"),
    "user": os.getenv("PG_USER", "rag_user"),
    "password": os.getenv("PG_PASSWORD", "rag_pass"),
    "host": os.getenv("PG_HOST", "pgvector"),
    "port": int(os.getenv("PG_PORT", 5432)),
}

KB_PATH = os.getenv("KB_PATH", "./kb")
CHUNK_SIZE = 800        # chars per chunk
CHUNK_OVERLAP = 100     # overlap between chunks

# -------------------- DB SETUP --------------------
def ensure_schema():
    logging.info("Ensuring pgvector schema exists")
    conn = psycopg2.connect(**PGVECTOR_CONN)
    cur = conn.cursor()

    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    conn.commit()
    cur.close()
    conn.close()
    logging.info("Schema ready")

# -------------------- EMBEDDINGS --------------------
def embed_text(text: str) -> List[float]:
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/embed",
        json={
            "model": OLLAMA_EMBED_MODEL,
            "input": text,  # Correct key for embeddings API
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    emb = data.get("embeddings", [])
    if not emb or not emb[0]:
        raise ValueError(f"Ollama embedding response invalid: {data}")
    return emb[0]

# -------------------- CHUNKING --------------------
def chunk_text(text: str) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP
    return chunks

# -------------------- DB INSERT --------------------
def upsert_document(doc_id: str, content: str, embedding: List[float]):
    conn = psycopg2.connect(**PGVECTOR_CONN)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO documents (repo_name, content, embedding)
        VALUES (%s, %s, %s)
        ON CONFLICT (repo_name)
        DO UPDATE SET
            content = EXCLUDED.content,
            embedding = EXCLUDED.embedding;
        """,
        (doc_id, content, embedding),
    )
    conn.commit()
    cur.close()
    conn.close()

# -------------------- FILE INGESTION --------------------
def ingest_file(path: Path):
    logging.info(f"Ingesting file: {path}")
    text = path.read_text(errors="ignore")

    chunks = chunk_text(text)
    logging.info(f" → {len(chunks)} chunks")

    for idx, chunk in enumerate(chunks):
        doc_id = f"{path.name}::chunk-{idx}"
        payload = json.dumps({
            "source": str(path),
            "chunk": idx,
            "content": chunk
        })

        try:
            embedding = embed_text(payload)
        except Exception as e:
            logging.warning(f"Skipping document {doc_id}: {e}")
            continue

        upsert_document(doc_id, payload, embedding)

# -------------------- MAIN INGEST --------------------
def ingest():
    kb_root = Path(KB_PATH)
    if not kb_root.exists():
        raise RuntimeError(f"KB_PATH does not exist: {kb_root}")

    files = [
        p for p in kb_root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".md", ".txt", ".json", ".yaml", ".yml"}
    ]

    logging.info(f"Found {len(files)} files")

    for f in files:
        try:
            ingest_file(f)
        except Exception as e:
            logging.error(f"Failed to ingest {f}: {e}")

    logging.info("Knowledge base ingestion complete")

# -------------------- ENTRY --------------------
if __name__ == "__main__":
    ensure_schema()
    ingest()
