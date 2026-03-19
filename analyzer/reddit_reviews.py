from __future__ import annotations

import re
from typing import Any, Dict, List

import requests


def _search_reddit(query: str, subreddit: str) -> List[Dict[str, Any]]:
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    params = {"q": query, "restrict_sr": "1", "sort": "relevance", "t": "year"}
    headers = {"User-Agent": "before-you-buy-bot/0.1"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    posts = []
    for child in data.get("data", {}).get("children", []):
        d = child.get("data", {})
        posts.append(
            {
                "title": d.get("title", ""),
                "url": "https://www.reddit.com" + d.get("permalink", ""),
                "selftext": d.get("selftext", ""),
                "score": d.get("score", 0),
            }
        )
    return posts


_POSITIVE_PAT = re.compile(
    r"\b(love|great|awesome|reliable|solid|no issues|highly recommend)\b",
    re.I,
)
_NEGATIVE_PAT = re.compile(
    r"\b(hate|terrible|awful|regret|problem|issue|broke|fail|lemon)\b",
    re.I,
)


def get_reddit_snippets(product: str, category: str) -> Dict[str, Any]:
    if not product:
        return {"snippets": [], "positives": 0, "negatives": 0}

    subreddits = ["askcarsales", "cars"]

    all_posts: List[Dict[str, Any]] = []
    for sr in subreddits:
        all_posts.extend(_search_reddit(product, sr))

    snippets = []
    positives = 0
    negatives = 0

    for p in all_posts[:15]:
        text = (p.get("title", "") + " " + p.get("selftext", ""))[:500]
        pos = bool(_POSITIVE_PAT.search(text))
        neg = bool(_NEGATIVE_PAT.search(text))
        if pos:
            positives += 1
        if neg:
            negatives += 1
        if pos or neg:
            snippets.append(
                {
                    "text": text[:280] + ("..." if len(text) > 280 else ""),
                    "url": p.get("url", ""),
                    "positive": pos,
                    "negative": neg,
                }
            )

    return {
        "snippets": snippets,
        "positives": positives,
        "negatives": negatives,
    }

