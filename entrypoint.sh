#!/bin/bash
set -e

MODEL_LLM="${OLLAMA_LLM_MODEL:-llama3.2}"
MODEL_EMBED="${OLLAMA_EMBED_MODEL:-nomic-embed-text}"

echo "Starting Ollama..."
ollama serve &
OLLAMA_PID=$!

echo "Waiting for Ollama API..."
until curl -sf http://localhost:11434/api/tags > /dev/null; do
  sleep 1
done

echo "Pulling models if missing..."
ollama list | grep -q "$MODEL_LLM" || ollama pull "$MODEL_LLM"
ollama list | grep -q "$MODEL_EMBED" || ollama pull "$MODEL_EMBED"

echo "Ollama ready"

# Forward signals properly
trap "kill $OLLAMA_PID" SIGTERM SIGINT

wait $OLLAMA_PID

