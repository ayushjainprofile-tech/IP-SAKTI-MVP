"""Tool interfaces kept independent from any specific search provider."""
from __future__ import annotations
import re
from typing import Any, Dict, Iterable, List
from .web_search_agent import search_web
from .source_validator import validate_sources


def web_search(query: str, domains: List[str] | None = None, max_results: int = 5) -> Dict[str, Any]:
    return search_web(query, domains=domains, max_results=max_results)


def official_source_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    official = ["ipindia.gov.in", "indiacode.nic.in", "wipo.int", "cbd.int", "ayush.gov.in", "fssai.gov.in", "egazette.nic.in"]
    result = search_web(query + " official government legislation", domains=official, max_results=max_results)
    result["official_only_requested"] = True
    return result


def source_validation(results: Iterable[Dict[str, Any]], query: str = "", domain: str = "") -> List[Dict[str, Any]]:
    return validate_sources(results, query=query, domain=domain)


def evidence_deduplication(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for item in items:
        key = str(item.get("url") or item.get("source") or item.get("title") or "").strip().lower()
        key = re.sub(r"[?#].*$", "", key)
        if key and key not in seen:
            seen.add(key); out.append(item)
    return out


def contradiction_detection(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for x in items:
        claim = str(x.get("claim") or x.get("title") or "").lower()
        tokens = tuple(sorted(set(re.findall(r"\b[a-z]{4,}\b", claim)) & {"allowed", "prohibited", "required", "exempt", "eligible", "patentable", "not"}))
        if tokens: grouped.setdefault(" ".join(tokens), []).append(x)
    contradictions = []
    for key, group in grouped.items():
        texts = [str(x.get("content") or x.get("snippet") or "").lower() for x in group]
        if any("not " in t for t in texts) and any("required" in t or "allowed" in t or "eligible" in t for t in texts):
            contradictions.append({"topic": key, "sources": [x.get("url") for x in group], "status": "POTENTIAL_CONTRADICTION", "requires_human_review": True})
    return contradictions
