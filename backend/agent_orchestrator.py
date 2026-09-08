"""Additive Agentic AI orchestrator for IP-SAKTI."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Any, Dict, List
from .agent_tools import web_search, source_validation, evidence_deduplication, contradiction_detection
from .legal_research_agent import build_research_plan

@dataclass
class AgenticResearchResult:
    status: str
    research_triggered: bool
    research_tasks: List[Dict[str, Any]]
    web_evidence: List[Dict[str, Any]]
    validated_sources: List[Dict[str, Any]]
    contradictions: List[Dict[str, Any]]
    confidence: Dict[str, Any]
    abstained: bool
    reason: str = ""
    missing_information: List[str] | None = None
    recommended_human_review: str = ""
    agents_used: List[str] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _needs_research(existing: List[Dict[str, Any]], validation: Dict[str, Any], product: Dict[str, Any]) -> tuple[bool, str]:
    status = str(validation.get("status", "")).upper()
    if not existing: return True, "No local evidence was retrieved."
    if status in {"INSUFFICIENT", "PARTIAL", "NOT_RUN", "FAILED", "ERROR"}: return True, f"Existing validation status is {status}."
    if validation.get("unsupported_domains"): return True, "One or more routed domains lack sufficient support."
    if str(product.get("jurisdiction", "India")).lower() == "india" and any(w in str(product.get("purpose", "")).lower() for w in ("current", "latest", "recent", "amendment", "notification")):
        return True, "The request explicitly requires current information."
    if any(str(x.get("authority_tier", 4)) != "1" for x in existing) and len(existing) < 3: return True, "Existing evidence is not sufficiently authoritative/dense."
    return False, "Existing evidence is considered sufficient for this stage."


def run_agentic_research(product: Dict[str, Any] | Any, existing_evidence: List[Dict[str, Any]] | None = None, validation: Dict[str, Any] | None = None) -> AgenticResearchResult:
    if hasattr(product, "model_dump"): product = product.model_dump()
    existing_evidence = existing_evidence or []
    validation = validation or {}
    needed, reason = _needs_research(existing_evidence, validation, product)
    if not needed:
        return AgenticResearchResult("SKIPPED", False, [], [], [], [], {"level": "HIGH", "score": 0.85, "basis": reason}, False, reason, [], "No additional human review triggered by agentic stage.", [])
    plan = build_research_plan(product, existing_evidence, validation)
    tasks = plan["tasks"]
    web_evidence: List[Dict[str, Any]] = []
    failures = []
    with ThreadPoolExecutor(max_workers=min(4, len(tasks) or 1)) as pool:
        futures = {pool.submit(web_search, f"{t['question']} Product: {product.get('product_name','')}; Ingredients: {', '.join(product.get('ingredients', []))}; Jurisdiction: {product.get('jurisdiction','India')}"): t for t in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                result = future.result()
                for item in result.get("results", []):
                    web_evidence.append({**item, "agent": task["agent"], "domain": task["domain"], "research_question": task["question"]})
                if result.get("status") == "ERROR": failures.append(task["agent"])
            except Exception:
                failures.append(task["agent"])
    web_evidence = evidence_deduplication(web_evidence)
    validated = source_validation(web_evidence, query=product.get("purpose", ""), domain="")
    validated = [x for x in validated if x.get("validated")]
    contradictions = contradiction_detection(validated)
    tier1 = [x for x in validated if x.get("authority_tier") == 1]
    score = min(1.0, (0.45 if tier1 else 0.0) + min(len(validated), 5) * 0.1 - min(len(contradictions), 3) * 0.1)
    abstained = not validated
    return AgenticResearchResult(
        "ABSTAIN" if abstained else "SUCCESS",
        True, tasks, web_evidence, validated, contradictions,
        {"level": "HIGH" if score >= .75 else "MEDIUM" if score >= .5 else "LOW", "score": round(max(0.0, score), 3), "tier1_sources": len(tier1), "failed_agents": failures},
        abstained,
        "No reliable authoritative web evidence was verified." if abstained else reason,
        ["Authoritative source", "Current amendment/notification", "Exact product claim/context"] if abstained else [],
        "Human/legal verification is recommended before a consequential decision." if abstained or contradictions else "",
        sorted(set(t["agent"] for t in tasks)),
    )
