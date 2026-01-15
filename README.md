# ai-rag-chatbot

A simple, self-hosted Slack chatbot that uses **Retrieval-Augmented Generation (RAG)** to answer questions from your internal documentation.

The bot runs fully on your infrastructure using Docker, connects to Slack, queries a vector database for relevant knowledge, and uses a local LLM (Ollama) to generate answers.

---

## High-level Architecture

```
Slack User
   |
   v
Slack App (Events API)
   |
   v
Slackbot (Flask App)
   |
   +--> Vector DB (Postgres + pgvector)  <- Knowledge Base
   |
   v
Ollama LLM (local model)
   |
   v
Answer back to Slack
```

---

## What This Project Does

* Receives messages from Slack
* Converts the user question into embeddings
* Searches a **vector database** for relevant content
* Sends retrieved context + question to a local LLM
* Responds back to Slack with a grounded answer

No external LLM APIs are required.

---

## Tech Stack

* **Slack** – User interface
* **Python + Flask** – Slackbot service
* **Ollama** – Local LLM runtime
* **PostgreSQL + pgvector** – Vector database
* **Docker & Docker Compose** – Deployment

---

## Components

### Slackbot Service

* Handles Slack Events API
* Calls Ollama for embeddings and generation
* Queries pgvector for relevant documents

### Ollama

* Runs local models (e.g. `llama3.2`)
* Provides `/embed` and `/generate` APIs

### Vector Database

* Stores document chunks and embeddings
* Enables semantic search using pgvector

---

## Knowledge Base (KB)

* Documentation is downloaded using scripts
* Content is split into small text chunks
* Each chunk is embedded using Ollama
* Embeddings are stored in Postgres (pgvector)

This allows fast semantic retrieval during chat.

---

## Running the Project

```bash
docker compose up --build
```

Services started:

* Slackbot (Flask)
* Ollama (LLM runtime)
* Postgres + pgvector (vector DB)

---

## Slack Setup (Summary)

1. Create a Slack App
2. Enable **Events API**
3. Subscribe to `message.channels`
4. Add Bot Token Scopes:

   * `app_mentions:read`
   * `chat:write`
5. Set Event Request URL to:

   ```
   http://<host>:3000/slack/events
   ```
For Reference: https://medium.com/@nagachetan.km/building-a-slack-bot-powered-by-ollamas-llama-3-in-docker-a4f11f72617d 

---

## Why RAG?

* Keeps answers grounded in your documentation
* No model retraining needed
* Easy to update knowledge by re-indexing docs

---

## Repository

GitHub:
[https://github.com/nagachetan/ai-rag-chatbot](https://github.com/nagachetan/ai-rag-chatbot)

---

## Who Is This For?

* Teams running on-prem or air-gapped systems
* Anyone wanting a private Slack AI assistant
* Learning RAG with minimal infrastructure

---

## License

MIT

