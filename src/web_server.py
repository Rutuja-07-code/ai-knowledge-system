import json
import os
import sys
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from knowledge_service import KnowledgeService

BASE_DIR = CURRENT_DIR.parent
WEB_DIR = BASE_DIR / "web"
service = KnowledgeService()
service_lock = threading.Lock()

app = FastAPI(title="AI Knowledge System")


@app.middleware("http")
async def disable_cache(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/api/status")
async def api_status():
    return service.get_status()


@app.get("/api/articles")
async def api_articles():
    return {"articles": service.articles}


@app.post("/api/refresh")
async def api_refresh(request: Request):
    payload = await _read_json_body(request)
    selected_interests = (payload or {}).get("selected_interests")
    interest_keywords = (payload or {}).get("interest_keywords")

    try:
        with service_lock:
            refresh_result = service.refresh_articles(
                selected_interests=selected_interests,
                interest_keywords=interest_keywords,
            )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    message = "Knowledge base refreshed successfully."
    if refresh_result["keywords_applied"]:
        message = "Knowledge base refreshed and filtered to your typed interests."
    elif refresh_result["keywords_fallback"]:
        message = (
            "No articles matched the typed interests exactly, so the full feed set was kept."
        )
    elif selected_interests:
        message = (
            "Knowledge base refreshed with all news. Your selected interests are prioritized at the top."
        )

    return {
        "message": message,
        "status": service.get_status(),
        "articles": refresh_result["articles"],
    }


@app.post("/api/ask")
async def api_ask(request: Request):
    payload = await _read_json_body(request)
    question = (payload or {}).get("question", "").strip()
    if not question:
        return JSONResponse(
            {"error": "Please enter a question before submitting."},
            status_code=400,
        )

    with service_lock:
        result = service.ask(question)

    return result


@app.post("/api/summarize")
async def api_summarize(request: Request):
    payload = await _read_json_body(request)
    article_link = (payload or {}).get("article_link", "").strip()
    if not article_link:
        return JSONResponse(
            {"error": "Please provide an article_link to summarize."},
            status_code=400,
        )

    with service_lock:
        summary = service.summarize_article(article_link)

    if summary is None:
        return JSONResponse(
            {"error": "Article not found in the knowledge base."},
            status_code=404,
        )

    return {"summary": summary}


@app.post("/api/search")
async def api_search(request: Request):
    payload = await _read_json_body(request)
    query = (payload or {}).get("query", "").strip()
    limit = int((payload or {}).get("limit", 10))
    if not query:
        return JSONResponse(
            {"error": "Please provide a search query."},
            status_code=400,
        )

    # Track the search event
    service.track_event(event_type="search", query=query)

    with service_lock:
        results = service.search_articles(query, limit=limit)

    search_history = service.get_search_history(limit=8)
    return {"results": results, "search_history": search_history}


@app.get("/api/recommendations")
async def api_recommendations():
    with service_lock:
        recommendations = service.get_recommendations(limit=8)
    return {"recommendations": recommendations}


@app.get("/api/trending")
async def api_trending():
    with service_lock:
        trending = service.get_trending_topics(limit=12)
    return {"trending": trending}


@app.post("/api/track")
async def api_track(request: Request):
    payload = await _read_json_body(request)
    event_type = (payload or {}).get("event_type", "").strip()
    if event_type not in ("click", "search"):
        return JSONResponse(
            {"error": "event_type must be 'click' or 'search'."},
            status_code=400,
        )

    service.track_event(
        event_type=event_type,
        article_link=(payload or {}).get("article_link"),
        query=(payload or {}).get("query"),
        category=(payload or {}).get("category"),
    )
    return {"status": "tracked"}


@app.post("/api/credibility")
async def api_credibility(request: Request):
    payload = await _read_json_body(request)
    article_link = (payload or {}).get("article_link", "").strip()
    if not article_link:
        return JSONResponse(
            {"error": "Please provide an article_link to check."},
            status_code=400,
        )

    with service_lock:
        result = service.detect_credibility(article_link)

    if result is None:
        return JSONResponse(
            {"error": "Article not found in the knowledge base."},
            status_code=404,
        )

    return result


async def _read_json_body(request: Request):
    try:
        return await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


def run(host=None, port=None):
    host = host or os.getenv("HOST", "0.0.0.0")
    port = int(port or os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
