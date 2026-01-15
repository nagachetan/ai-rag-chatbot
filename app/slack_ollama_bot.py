#!/usr/bin/env python3

import os
import json
import uuid
import requests
import time
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from flask import Flask, request, jsonify
import structlog
from typing import List

# -------------------- STRUCTURED LOGGING --------------------
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()

# -------------------- APP --------------------
app = Flask(__name__)

# -------------------- CONFIG --------------------
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

# Distance thresholds
STRONG_THRESHOLD = -0.85  # very similar
SOFT_THRESHOLD = -0.5     # somewhat similar

# Verify Model Check
MODEL_LAST_OK = 0
MODEL_CHECK_TTL = 300  # seconds (5 minutes)

PGVECTOR_CONN = {
    "dbname": os.getenv("PG_DB", "postgres"),
    "user": os.getenv("PG_USER", "rag_user"),
    "password": os.getenv("PG_PASSWORD", "rag_pass"),
    "host": os.getenv("PG_HOST", "pgvector"),
    "port": int(os.getenv("PG_PORT", 5432)),
}

PORT = int(os.getenv("PORT", 3001))
ENABLE_CITATIONS = os.getenv("ENABLE_CITATIONS", "true").lower() == "true"

logger.info("Starting Slack Ollama RAG bot", port=PORT)

# -------------------- DB POOL --------------------
pg_pool = SimpleConnectionPool(1, 10, **PGVECTOR_CONN)

def get_conn():
    return pg_pool.getconn()

def put_conn(conn):
    pg_pool.putconn(conn)

# -------------------- OLLAMA --------------------
def embed_text(text: str) -> List[float]:
    logger.debug("Embedding request", text_len=len(text))
    r = requests.post(
        f"{OLLAMA_BASE_URL}/api/embed",
        json={"model": OLLAMA_EMBED_MODEL, "input": text},
        timeout=30,
    )
    r.raise_for_status()
    emb = r.json()["embeddings"][0]
    logger.debug("Embedding received", dim=len(emb))
    return emb

def call_llm(prompt: str) -> str:
    """
    Streaming-safe LLM call.
    """
    logger.debug("LLM call", prompt_len=len(prompt))
    r = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={"model": OLLAMA_LLM_MODEL, "prompt": prompt, "temperature": 0},
        stream=True,
        timeout=60,
    )
    r.raise_for_status()
    out = ""
    for line in r.iter_lines():
        if line:
            try:
                data = json.loads(line.decode())
                out += data.get("response", "")
            except json.JSONDecodeError:
                continue
    logger.debug("LLM response complete", length=len(out))
    return out.strip()

# -------------------- VECTOR QUERY --------------------
def vector_db_query(vec: List[float], top_k=5):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT repo_name, content, embedding <#> %s::vector AS distance
            FROM documents
            ORDER BY distance
            LIMIT %s
            """,
            (vec, top_k),
        )
        rows = cur.fetchall()
        return [
            {
                "repo_name": r[0],
                "content": r[1],
                "distance": float(r[2]),
            }
            for r in rows
        ]
    finally:
        put_conn(conn)

# -------------------- RETRIEVAL --------------------
def retrieve_context(query: str, top_k=5):
    vec = embed_text(query)
    results = vector_db_query(vec, top_k)

    # Strong matches
    strong = [r for r in results if r["distance"] <= STRONG_THRESHOLD]

    # Soft matches (include moderate similarity)
    weak = [r for r in results if STRONG_THRESHOLD < r["distance"] <= SOFT_THRESHOLD]

    # Decide which contexts to use
    if strong:
        contexts = strong
        logger.info("Using strong KB matches", total=len(results), strong=len(strong))
    elif weak:
        contexts = weak
        logger.info("Using weak KB matches", total=len(results), weak=len(weak))
    else:
        contexts = []
        logger.info("No relevant KB match; will fallback to LLM", total=len(results))

    return contexts

# -------------------- PROMPTS --------------------
def build_kb_prompt(question: str, contexts: list[dict]) -> str:
    """
    Combine KB facts into prompt.
    """
    facts = "\n".join(c["content"] for c in contexts)
    citations = ""
    if ENABLE_CITATIONS:
        citations = "\n\nCitations:\n" + "\n".join(
            f"{c['repo_name']}" for c in contexts
        )

    return f"""
Answer the question using ONLY the facts below.

Facts:
{facts}

Question:
{question}

Rules:
- Combine facts naturally
- If the question contradicts the facts, say so
- If info is missing, say "not mentioned"
- Do NOT invent new facts

Answer concisely in 1-2 sentences:
{citations}
""".strip()

def build_fallback_prompt(question: str) -> str:
    return f"""
Answer the question based on general knowledge only.
Do NOT assume facts from KB if not present.

Question:
{question}

Answer:
""".strip()

# -------------------- /ASK --------------------
@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Missing query"}), 400

    session = data.get("session", "default")
    request_id = str(uuid.uuid4())

    logger.info("Ask received", q=query, session=session, request_id=request_id)

    contexts = retrieve_context(query)

    # Separate strong and weak matches
    strong_contexts = [c for c in contexts if c["distance"] <= STRONG_THRESHOLD]
    weak_contexts = [c for c in contexts if STRONG_THRESHOLD < c["distance"] <= SOFT_THRESHOLD]

    # -------------------- Decide mode --------------------
    if strong_contexts:
        mode = "KB"
        prompt = build_kb_prompt(query, strong_contexts)

    elif weak_contexts:
        # Use weak matches only if they **contain query terms or proper answer info**
        # Heuristic: check if any proper nouns / key info from query appear in content
        def is_relevant(c):
            return any(word.lower() in c["content"].lower() for word in query.split() if len(word) > 3)

        relevant_weak = [c for c in weak_contexts if is_relevant(c)]

        if relevant_weak:
            mode = "KB"
            prompt = build_kb_prompt(query, relevant_weak)
        else:
            mode = "FALLBACK"
            prompt = build_fallback_prompt(query)
            hint_text = "\n".join(c["content"] for c in weak_contexts)
            if hint_text:
                prompt += "\n\n(Optional facts that might be related but not confirmed):\n" + hint_text

    else:
        mode = "FALLBACK"
        prompt = build_fallback_prompt(query)

    answer = call_llm(prompt)

    return jsonify({
        "query": query,
        "answer": answer,
        "mode": mode,
        "context_used": len(contexts),
        "request_id": request_id,
        "session": session,
    })

# -------------------- HEALTH --------------------
@app.route("/health")
def health():
    model_ok = verify_model(OLLAMA_LLM_MODEL)

    return jsonify({
        "status": "ok" if model_ok else "degraded",
        "ollama_model": OLLAMA_LLM_MODEL,
        "model_available": model_ok,
    }), 200

def verify_model(model):
    global MODEL_LAST_OK

    # Skip frequent checks
    if time.time() - MODEL_LAST_OK < MODEL_CHECK_TTL:
        return True

    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model,
                "prompt": "ping",
                "options": {
                    "num_predict": 1
                }
            },
            timeout=5,
        )

        if r.status_code == 200:
            MODEL_LAST_OK = time.time()
            return True

        return False

    except Exception:
        return False

# -------------------- MAIN --------------------
if __name__ == "__main__":
    if not verify_model(OLLAMA_LLM_MODEL):
        raise RuntimeError(f"Ollama model not available at startup: {OLLAMA_LLM_MODEL}")

    app.run(host="0.0.0.0", port=PORT)

