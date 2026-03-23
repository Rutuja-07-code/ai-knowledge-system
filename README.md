# AI Knowledge System

This project now includes a browser-based frontend for refreshing the article
pipeline, browsing indexed news, and asking questions against the local
knowledge base. Article persistence now uses SQLite, with automatic import from
the legacy `articles.json` file on first run.

## Run the frontend

1. Install the dependencies in `requirements.txt`.
2. Start the web server:

```bash
uvicorn src.web_server:app --reload
```

3. Open `http://127.0.0.1:8000` in your browser.

Do not open `web/index.html` directly from the filesystem. The frontend needs
the Python API routes from `src/web_server.py` in order to load articles.

This project now uses FastAPI for the backend and serves the frontend assets
through the FastAPI app.

## What the app does

- Loads existing articles from SQLite
- Rebuilds the vector index on startup
- Refreshes RSS feeds and saves the latest articles into `data/knowledge.db`
- Lets the user choose which news interests to refresh before pulling articles
- Uses Ollama to generate answers from the top matching sources
- Returns related topics and related coverage for each question

## Ollama

- Default model: `phi:latest`
- Default Ollama URL: `http://127.0.0.1:11434`
- Optional environment variables:
  - `OLLAMA_MODEL`
  - `OLLAMA_URL`
  - `OLLAMA_TIMEOUT`

If `OLLAMA_URL` is not reachable, the app falls back to a non-LLM answer path.

## Deploy on Render

This repo now includes a root-level `render.yaml` for Render Blueprint deploys.

- Start command: `uvicorn src.web_server:app --host 0.0.0.0 --port $PORT`
- Render port binding: automatic through the `PORT` environment variable
- SQLite path on Render: `/var/data/knowledge.db`
- Persistent disk mount path in the Blueprint: `/var/data`

Important:
- If you want Ollama-generated answers on Render, set `OLLAMA_URL` to a reachable Ollama service.
- If you do not set `OLLAMA_URL`, the app still deploys, but generated answers fall back to the non-LLM path.
- Using SQLite without a persistent disk means your data will not survive redeploys or restarts.

## Database

- SQLite database path: `data/knowledge.db`
- Main table: `articles`
- Metadata table: `metadata`
- Legacy JSON import: automatic on first startup if the database is empty

## Project structure

- `src/web_server.py`: FastAPI app and API routes
- `src/knowledge_service.py`: persistence, indexing, and query orchestration
- `src/database/article_store.py`: SQLite storage and JSON migration
- `web/`: static frontend assets
