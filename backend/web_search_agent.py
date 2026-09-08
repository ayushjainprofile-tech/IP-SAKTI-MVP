"""Pluggable web search agent. No credentials are hard-coded."""
from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen
from urllib.parse import quote_plus
from typing import Any, Dict, List

SEARCH_DOMAINS = [
    "ipindia.gov.in", "indiacode.nic.in", "egazette.nic.in", "wipo.int", "cbd.int",
    "ayush.gov.in", "fssai.gov.in", "plantauthority.gov.in", "dbtindia.gov.in",
    "moef.gov.in", "un.org", "who.int",
]

TOPICS = {
    "ip": "Indian patent law rules GI trademarks copyright designs plant variety protection WIPO TRIPS PCT Madrid Hague Budapest",
    "tk": "traditional knowledge India Section 3(p) WIPO GRATK Treaty TK databases biodiversity",
    "abs": "Biological Diversity Act access benefit sharing Nagoya Protocol CBD India rules regulations",
    "regulatory": "AYUSH FSSAI Ayurveda-Aahar Drugs Cosmetics Rules India notifications amendments",
}


def _request_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: int) -> Dict[str, Any]:
    req = Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **headers}, method="POST")
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _tavily(query: str, max_results: int, timeout: int) -> List[Dict[str, Any]]:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        return []
    body = {"api_key": key, "query": query, "search_depth": os.getenv("AGENTIC_SEARCH_DEPTH", "advanced"), "max_results": max_results, "include_answer": False}
    data = _request_json("https://api.tavily.com/search", body, {}, timeout)
    return [{"title": x.get("title", ""), "url": x.get("url", ""), "content": x.get("content", ""), "published_at": x.get("published_date")} for x in data.get("results", [])]


def search_web(query: str, *, domains: List[str] | None = None, max_results: int = 5, timeout: int = 12) -> Dict[str, Any]:
    """Use Tavily when configured; otherwise fail closed with an empty result set."""
    query = str(query).strip()[:1800]
    if not query:
        return {"status": "NO_QUERY", "results": []}
    try:
        results = _tavily(query, max_results, timeout)
        return {"status": "SUCCESS" if results else "NO_PROVIDER_OR_RESULTS", "provider": "tavily" if results else None, "query": query, "results": results}
    except Exception as exc:
        return {"status": "ERROR", "provider": "tavily", "query": query, "results": [], "error": type(exc).__name__}


def build_targeted_queries(product: Dict[str, Any], domains: List[str]) -> List[Dict[str, Any]]:
    base = f"{product.get('product_name','')} ingredients: {', '.join(product.get('ingredients', []))} purpose: {product.get('purpose','')} jurisdiction: {product.get('jurisdiction','India')}"
    tasks = []
    for domain in domains or ["ip"]:
        topic = TOPICS.get(domain.lower(), TOPICS["ip"])
        tasks.append({"agent": f"{domain.upper()} Research", "domain": domain.upper(), "query": f"{base}. Research authoritative current sources on {topic}."})
    tasks.append({"agent": "Web Research", "domain": "REGULATORY", "query": f"{base}. Find current official laws, rules, notifications, amendments and regulator guidance relevant to classification and claims."})
    return tasks
