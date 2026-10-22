import html
import logging
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

USER_AGENT = "DocuMind-FactChecker/1.0 (academic innovation competition; contact: documind@example.com)"

class SourceRetriever:
    """Retrieves verifiable evidence snippets from free APIs (Google Fact Check, Wikipedia, Tavily)."""

    def __init__(self, factcheck_api_key: Optional[str] = None, tavily_api_key: Optional[str] = None):
        self.factcheck_api_key = factcheck_api_key or os.environ.get("FACTCHECK_API_KEY", "").strip()
        self.tavily_api_key = tavily_api_key or os.environ.get("TAVILY_API_KEY", "").strip()

    def retrieve_evidence(self, query: str) -> List[Dict[str, Any]]:
        """Queries free web sources and returns standardized, numbered evidence items."""
        evidence_items = []
        clean_q = query.strip()
        if not clean_q:
            return []

        # 1. Google Fact Check Tools API (if key is set)
        if self.factcheck_api_key:
            gfc_items = self._query_google_factcheck(clean_q)
            evidence_items.extend(gfc_items)

        # 2. Wikipedia (Completely Free, No Key Required)
        wiki_items = self._query_wikipedia(clean_q)
        evidence_items.extend(wiki_items)

        # 3. Tavily API (Optional extra source, if key is set)
        if self.tavily_api_key:
            tavily_items = self._query_tavily(clean_q)
            evidence_items.extend(tavily_items)

        # Assign 1-based sequential evidence IDs for the LLM judge
        formatted = []
        for idx, item in enumerate(evidence_items, start=1):
            formatted.append({
                "evidence_id": idx,
                "title": item["title"],
                "url": item["url"],
                "snippet": item["snippet"],
                "source_type": item["source_type"],
            })

        return formatted

    def _query_google_factcheck(self, query: str) -> List[Dict[str, Any]]:
        """Queries Google Fact Check Tools claims:search endpoint."""
        url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
        params = {
            "query": query[:120],  # Shorten for search index
            "languageCode": "en",
            "key": self.factcheck_api_key,
        }
        results = []
        try:
            resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                for c in data.get("claims", [])[:3]:
                    for r in c.get("claimReview", [])[:2]:
                        publisher = r.get("publisher", {}).get("name", "Fact Checker")
                        title = r.get("title") or f"Fact Check by {publisher}"
                        link = r.get("url")
                        rating = r.get("textualRating", "Unrated")
                        claim_text = c.get("text", "")
                        snippet = f"Claim: {claim_text}. Rating by {publisher}: {rating}."

                        if link and snippet:
                            results.append({
                                "title": title,
                                "url": link,
                                "snippet": snippet,
                                "source_type": "google_factcheck",
                            })
        except Exception as e:
            logger.warning(f"Google Fact Check API query failed: {e}")

        return results

    def _query_wikipedia(self, query: str) -> List[Dict[str, Any]]:
        """Queries Wikipedia MediaWiki Action API for factual articles and extracts."""
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query[:100],
            "utf8": "",
            "format": "json",
            "srlimit": 3,
        }
        results = []
        try:
            resp = requests.get(search_url, params=params, headers={"User-Agent": USER_AGENT}, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                search_hits = data.get("query", {}).get("search", [])

                for hit in search_hits:
                    title = hit.get("title", "")
                    raw_snippet = hit.get("snippet", "")

                    # Strip MediaWiki HTML tags (e.g. <span class="searchmatch">)
                    clean_snippet = re.sub(r"<[^>]+>", "", raw_snippet)
                    clean_snippet = html.unescape(clean_snippet).strip()

                    title_encoded = urllib.parse.quote(title.replace(" ", "_"))
                    page_url = f"https://en.wikipedia.org/wiki/{title_encoded}"

                    if title and clean_snippet:
                        results.append({
                            "title": f"Wikipedia: {title}",
                            "url": page_url,
                            "snippet": clean_snippet,
                            "source_type": "wikipedia",
                        })
        except Exception as e:
            logger.warning(f"Wikipedia API query failed: {e}")

        return results

    def _query_tavily(self, query: str) -> List[Dict[str, Any]]:
        """Queries Tavily Search API as an optional extra source."""
        url = "https://api.tavily.com/search"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.tavily_api_key}",
            "User-Agent": USER_AGENT,
        }
        payload = {
            "query": query,
            "search_depth": "basic",
            "max_results": 3,
        }
        results = []
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("results", [])[:3]:
                    title = item.get("title", "Web Source")
                    link = item.get("url")
                    content = item.get("content", "").strip()
                    if link and content:
                        results.append({
                            "title": title,
                            "url": link,
                            "snippet": content[:300],
                            "source_type": "tavily",
                        })
        except Exception as e:
            logger.warning(f"Tavily API query failed: {e}")

        return results
