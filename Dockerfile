FROM python:3.11-slim

# System deps (minimal)
RUN apt-get update && apt-get install -y \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app/ ./app/
COPY wait-for-postgres.sh .
COPY .env .

RUN chmod +x wait-for-postgres.sh \
    && chmod +x app/slack_ollama_bot.py

EXPOSE 3000

CMD ["./wait-for-postgres.sh", "pgvector", "python3", "-u", "app/slack_ollama_bot.py"]

