import json

import feedparser
import requests

try:
    from newspaper import Article
except ImportError:
    Article = None

INTEREST_FEEDS = {
    "technology": {
        "label": "Technology",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    },
    "science": {
        "label": "Science",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
    },
    "world": {
        "label": "World",
        "url": ["https://rss.nytimes.com/services/xml/rss/nyt/world.xml",
                 "http://feeds.bbci.co.uk/news/world/rss.xml",
                 "https://www.aljazeera.com/xml/rss/all.xml",]
    },
    # NEW
    "business": {
        "label": "Business",
        "url": ["https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"],
    },
    "health": {
        "label": "Health",
        "url": ["https://rss.nytimes.com/services/xml/rss/nyt/Health.xml"],
    },
    "sports": {
        "label": "Sports",
        "url": ["http://feeds.bbci.co.uk/sport/rss.xml"],
    },
    "ai_ml": {
        "label": "AI & Machine Learning",
        "url": [
            "https://news.google.com/rss/search?q=artificial+intelligence",
            "https://machinelearningmastery.com/feed/",
        ],
    },
    "climate": {
        "label": "Climate & Environment",
        "url": ["https://rss.nytimes.com/services/xml/rss/nyt/Climate.xml"],
    },
}


HEADERS = {
    "User-Agent": "Mozilla/5.0",
}


def extract_rss_content(entry):
    if entry.get("summary"):
        return entry.summary

    content_items = entry.get("content", [])
    if content_items:
        return content_items[0].get("value", "")

    return ""


def _fetch_article_content(url):
    if Article is None:
        return ""

    try:
        news_article = Article(url)
        news_article.download()
        news_article.parse()
        return news_article.text.strip()
    except Exception:
        return ""


def get_available_interests():
    return [
        {"key": key, "label": config["label"]}
        for key, config in INTEREST_FEEDS.items()
    ]


def normalize_interest_keys(selected_interests):
    if not selected_interests:
        return list(INTEREST_FEEDS.keys())

    normalized = []
    seen = set()

    for interest in selected_interests:
        key = str(interest).strip().lower()
        if key in INTEREST_FEEDS and key not in seen:
            normalized.append(key)
            seen.add(key)

    return normalized


def collect_news(selected_interests=None, limit_per_feed=10, timeout=10):
    articles = []
    seen_links = set()
    interest_keys = normalize_interest_keys(selected_interests)

    for interest_key in interest_keys:
        interest_config = INTEREST_FEEDS[interest_key]
        raw_url = interest_config["url"]

        # Normalize to a list so both single-string and list configs work
        feed_urls = raw_url if isinstance(raw_url, list) else [raw_url]

        for feed_url in feed_urls:
            try:
                response = requests.get(feed_url, headers=HEADERS, timeout=timeout)
                response.raise_for_status()
            except requests.RequestException:
                continue

            feed = feedparser.parse(response.content)

            for entry in feed.entries[:limit_per_feed]:
                article_url = entry.get("link", "").strip()
                if not article_url or article_url in seen_links:
                    continue

                seen_links.add(article_url)
                content = _fetch_article_content(article_url) or extract_rss_content(entry)

                articles.append(
                    {
                        "title": entry.get("title", "Untitled Article"),
                        "link": article_url,
                        "published": entry.get("published", ""),
                        "content": content.strip(),
                        "content_source": "article" if content else "rss",
                        "category": interest_config["label"],
                    }
                )

    return articles


def search_function(query, articles):
    query = query.lower()
    results = []

    for article in articles:
        haystack = " ".join(
            [
                article.get("title", "").lower(),
                article.get("content", "").lower(),
            ]
        )

        if query in haystack:
            results.append(article)

    return results


def save_to_json(data, path="articles.json"):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    news_data = collect_news()
    save_to_json(news_data)

    query = input("Ask a question: ")
    results = search_function(query, news_data)

    if not results:
        print("\nNo relevant news found.")
    else:
        print("\nRelevant News:")
        for index, article in enumerate(results, start=1):
            print(f"{index}. {article['title']} - {article['link']}")
