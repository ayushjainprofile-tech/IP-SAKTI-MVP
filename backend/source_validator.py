"""Source Validation Module for IP-SAKTI."""
import re
from typing import Any, Dict, Iterable, List


def validate_sources(results: Iterable[Dict[str, Any]], query: str = "", domain: str = "") -> List[Dict[str, Any]]:
    out = []
    query_tokens = set(re.findall(r"\w+", query.lower()))
    for item in results:
        title = str(item.get("title") or item.get("source") or "").strip()
        url = str(item.get("url") or "").strip()
        evidence = str(item.get("content") or item.get("snippet") or item.get("evidence_text") or "").strip()
        
        text_tokens = set(re.findall(r"\w+", f"{title} {evidence}".lower()))
        overlap = len(text_tokens & query_tokens) / max(len(query_tokens), 1) if query_tokens else 1.0
        
        is_official = any(ext in url.lower() for ext in [".gov", ".nic.in", "wipo.int", "cbd.int", "ayush.gov.in", "fssai.gov.in", ".org"])
        confidence = round(0.5 * (1.0 if is_official else 0.5) + 0.5 * overlap, 2)
        
        out.append({
            "source": title or url or "Unknown source",
            "title": title,
            "url": url,
            "domain": domain or "GENERAL",
            "confidence": confidence,
            "evidence_text": evidence,
            "validated": bool(evidence and confidence >= 0.3),
        })
    return sorted(out, key=lambda x: x.get("confidence", 0.0), reverse=True)
