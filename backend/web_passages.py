"""
Pick the web evidence that actually answers a chat question.

Tavily snippets from large official pages are often a navigation menu or an
unrelated clause, and validation ranks sources by authority alone. This
module ranks validated sources by how well their text matches the question,
drops site-menu boilerplate, and, for the top sources, pulls the full page
(Tavily Extract) and keeps the passage that best matches the question.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterable, List, Set, Tuple
from urllib.request import Request, urlopen

# Question words (English + Hinglish) -> terms an answering passage contains.
INTENTS: Dict[str, Tuple[Set[str], Set[str]]] = {
    "procedure": (
        {"how", "kaise", "kese", "process", "procedure", "steps", "step",
         "apply", "file", "filing", "register", "registration", "obtain", "get"},
        {"step", "steps", "procedure", "process", "file", "filing", "form",
         "application", "apply", "submit", "examination", "request", "fee",
         "fees", "grant", "publication", "specification", "provisional",
         "complete", "online", "e-filing", "portal"},
    ),
    "eligibility": (
        {"patentable", "eligible", "allowed", "can", "sakte", "sakta", "kya"},
        {"patentable", "not", "novel", "novelty", "inventive", "industrial",
         "section", "invention", "excluded", "exclusion"},
    ),
    "cost": (
        {"fee", "fees", "cost", "costs", "charges", "price", "kitna", "kitni", "paisa"},
        {"fee", "fees", "rs", "inr", "rupees", "charges", "amount", "payable"},
    ),
    "time": (
        {"time", "long", "duration", "kitne", "din", "kab", "months", "years"},
        {"months", "month", "years", "year", "days", "period", "within", "time"},
    ),
    "approval": (
        {"approval", "permission", "anumati", "nba", "sbb", "need", "required", "chahiye"},
        {"approval", "prior", "permission", "authority", "board", "nba", "sbb",
         "form", "apply", "benefit", "sharing", "required"},
    ),
}

STOPWORDS = {
    "the", "and", "for", "with", "what", "which", "who", "why", "when", "where",
    "are", "was", "were", "does", "did", "should", "would", "could", "will",
    "this", "that", "there", "their", "from", "into", "about", "india", "indian",
    "hai", "hain", "kare", "karen", "karein", "karna", "karte", "karu", "kar",
    "mai", "mein", "main", "me", "ka", "ki", "ke", "ko", "se", "aur", "bhi",
    "toh", "to", "ye", "yeh", "vo", "woh", "please", "tell", "explain", "batao",
    "bataiye", "samjhao", "any", "all", "our", "your", "you", "its",
}

PASSAGE_CHARS = 1600
EXTRACT_TOP_N = 3


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z][a-z0-9\-]{1,}", str(text or "").lower())


def question_terms(query: str) -> Tuple[Set[str], Set[str]]:
    """(topic terms the passage must mention, intent terms that answer it)."""
    words = set(_tokens(query))
    intent_terms: Set[str] = set()
    intent_words: Set[str] = set()
    for triggers, answers in INTENTS.values():
        hit = words & triggers
        if hit:
            intent_words |= hit
            intent_terms |= answers
    topic = {
        w for w in words
        if len(w) >= 3 and w not in STOPWORDS and w not in intent_words
    }
    return topic, intent_terms


STEP_MARKER = re.compile(
    r"\bstep\s*\d|\bstage\s*\d|\bform[\s-]?\d|^\s*(?:#+\s*)?\d{1,2}[.)]\s+[A-Z]",
    re.IGNORECASE | re.MULTILINE,
)


def step_markers(text: str) -> int:
    """Numbered steps / "Step 3" / "Form 2" markers: procedures look like this."""
    return len(STEP_MARKER.findall(str(text or "")))


def is_boilerplate(text: str) -> bool:
    """True for site navigation menus scraped as page content."""
    lines = [x.strip() for x in str(text or "").splitlines() if x.strip()]
    menu_marks = str(text or "").count(";)") + str(text or "").count("»")
    if menu_marks >= 3:
        return True
    if len(lines) < 6:
        return False
    short_items = sum(
        1 for x in lines
        if re.match(r"^[-+*•]\s", x) and len(x.split()) <= 6
    )
    return short_items / len(lines) > 0.5


def relevance(text: str, topic: Set[str], intent: Set[str]) -> float:
    """Share of topic terms present, plus answer-term density; 0 if off-topic."""
    words = _tokens(text)
    if not words:
        return 0.0
    present = set(words)
    if topic:
        topic_hit = len(topic & present) / len(topic)
        if topic_hit == 0:
            return 0.0
    else:
        topic_hit = 1.0
    # Distinct answer terms: a clause repeating "application" is not a procedure.
    intent_hits = len(intent & present)
    intent_score = min(1.0, intent_hits / 7.0) if intent else 0.0
    return round(topic_hit * (0.4 + 0.6 * intent_score if intent else 1.0), 4)


def best_passage(text: str, topic: Set[str], intent: Set[str],
                 size: int = PASSAGE_CHARS) -> Tuple[str, float]:
    """Highest-relevance window of the text, cut on paragraph boundaries."""
    text = re.sub(r"[ \t]+", " ", str(text or ""))
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[#\d]+[.)\s])", text) if p.strip()]
    paragraphs = [p for p in paragraphs if not is_boilerplate(p)]
    best, best_score = "", 0.0
    for i in range(len(paragraphs)):
        window, j = "", i
        while j < len(paragraphs) and len(window) + len(paragraphs[j]) <= size:
            window = (window + "\n" + paragraphs[j]).strip()
            j += 1
        if not window:
            window = paragraphs[i][:size]
        score = relevance(window, topic, intent)
        if score > best_score:
            best, best_score = window, score
    return best, best_score


def _extract_pages(urls: List[str], timeout: int) -> Dict[str, str]:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key or not urls:
        return {}
    req = Request(
        "https://api.tavily.com/extract",
        data=json.dumps({"api_key": key, "urls": urls}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "ip-sakti-backend/1.0"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return {
        str(x.get("url")): str(x.get("raw_content") or "")
        for x in data.get("results", []) or []
        if isinstance(x, dict)
    }


def rank_for_question(
    validated: Iterable[Dict[str, Any]],
    query: str,
    limit: int,
    extract: bool = True,
    timeout: int = 12,
) -> List[Dict[str, Any]]:
    """Validated web items, best answers first, with question-matched text.

    Falls back to the original order when the question has no usable terms
    (e.g. Devanagari only), and to the search snippet if extraction fails.
    """
    items = [dict(x) for x in validated]
    topic, intent = question_terms(query)
    procedural = "step" in intent
    if not topic and not intent:
        return items[:limit]

    for item in items:
        text = str(item.get("evidence_text") or item.get("content") or "")
        item["_relevance"] = 0.0 if is_boilerplate(text) else relevance(text, topic, intent)

    if extract:
        # Pull full pages for the strongest sources whose snippet is weak.
        candidates = sorted(
            items, key=lambda x: float(x.get("confidence", 0.0) or 0.0), reverse=True
        )
        urls = [
            str(x.get("url")) for x in candidates
            if x.get("url") and x["_relevance"] < 0.7
        ][:EXTRACT_TOP_N]
        try:
            pages = _extract_pages(urls, timeout)
        except Exception:
            pages = {}
        for item in items:
            page = pages.get(str(item.get("url")))
            if not page:
                continue
            passage, score = best_passage(page, topic, intent)
            if score > item["_relevance"]:
                item["evidence_text"] = passage
                item["_relevance"] = score
                item["passage_source"] = "full_page_extract"

    relevant = [x for x in items if x["_relevance"] > 0]
    pool = relevant or items
    # "How to" questions: among equally relevant sources, prefer ones that
    # actually lay out steps/forms over background text.
    pool.sort(
        key=lambda x: (
            x["_relevance"],
            min(step_markers(x.get("evidence_text", "")), 5) if procedural else 0,
            float(x.get("confidence", 0.0) or 0.0),
        ),
        reverse=True,
    )
    for x in pool:
        x["question_relevance"] = x.pop("_relevance")
    return pool[:limit]
