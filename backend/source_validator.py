"""Source authority, URL safety, relevance and confidence validation."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse
from typing import Any, Dict, Iterable, List

TIER1_SUFFIXES = (".gov.in", ".nic.in", ".gov", ".int")
TIER1_DOMAINS = {
    "wipo.int", "who.int", "un.org", "cbd.int", "fao.org", "ipindia.gov.in",
    "indiacode.nic.in", "egazette.nic.in", "ayush.gov.in", "fssai.gov.in",
    "nppaindia.nic.in", "plantauthority.gov.in", "dbtindia.gov.in", "moef.gov.in",
}
TIER2_HINTS = ("edu", "ac.in", "ac.uk", "research", "institute", "university")


def _host(url: str) -> str:
    return (urlparse(str(url)).hostname or "").lower().strip(".")


def validate_url(url: str) -> bool:
    try:
        p = urlparse(str(url))
        return p.scheme in {"http", "https"} and bool(p.hostname) and len(str(url)) <= 2048
    except Exception:
        return False


def authority_for_url(url: str) -> Dict[str, Any]:
    host = _host(url)
    if not host:
        return {"tier": 4, "label": "Unknown", "score": 0.1}
    if host in TIER1_DOMAINS or any(host.endswith(s) for s in TIER1_SUFFIXES):
        return {"tier": 1, "label": "Official / Government / Treaty", "score": 1.0}
    if any(x in host for x in TIER2_HINTS):
        return {"tier": 2, "label": "Academic / Institutional", "score": 0.8}
    if any(x in host for x in ("law", "legal", "ip", "consult", "firm")):
        return {"tier": 3, "label": "Professional secondary", "score": 0.55}
    return {"tier": 4, "label": "Blog / Unknown", "score": 0.25}


def _date_score(value: Any) -> float:
    if not value:
        return 0.45
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        age_days = max(0, (datetime.now(dt.tzinfo) - dt).days)
        return max(0.25, 1.0 - min(age_days, 3650) / 5000)
    except Exception:
        return 0.45


def validate_source(result: Dict[str, Any], query: str = "", domain: str = "") -> Dict[str, Any]:
    url = str(result.get("url", "")).strip()
    safe = validate_url(url)
    auth = authority_for_url(url) if safe else {"tier": 4, "label": "Invalid URL", "score": 0.0}
    text = " ".join(str(result.get(k, "")) for k in ("title", "content", "snippet")).lower()
    qwords = {w for w in query.lower().split() if len(w) > 3}
    overlap = len(qwords & set(text.split())) / max(len(qwords), 1)
    relevance = round(min(1.0, 0.7 * overlap + 0.3 * bool(domain and domain.lower() in text)), 3)
    confidence = round(0.55 * auth["score"] + 0.25 * relevance + 0.20 * _date_score(result.get("published_at") or result.get("updated_at")), 3)
    return {
        **result,
        "url": url,
        "authority": auth["label"],
        "authority_tier": auth["tier"],
        "relevance": relevance,
        "confidence": confidence,
        "url_valid": safe,
        "validated": bool(safe and confidence >= 0.35),
        "validation_note": "Authoritative source preferred" if auth["tier"] == 1 else "Secondary source; verify against Tier 1",
    }


def validate_sources(results: Iterable[Dict[str, Any]], query: str = "", domain: str = "") -> List[Dict[str, Any]]:
    out = [validate_source(r, query, domain) for r in results]
    return sorted(out, key=lambda x: (x.get("validated", False), -x.get("authority_tier", 9), x.get("confidence", 0)), reverse=True)
