"""Turns product context into bounded, evidence-seeking legal research tasks."""
from __future__ import annotations
from typing import Any, Dict, List


def build_research_plan(product: Dict[str, Any], existing_evidence: List[Dict[str, Any]], validation: Dict[str, Any]) -> Dict[str, Any]:
    ingredients = product.get("ingredients", [])
    purpose = str(product.get("purpose", ""))
    ptype = str(product.get("product_type", ""))
    tk = str(product.get("based_on_traditional_knowledge", "")).lower()
    jurisdiction = str(product.get("jurisdiction", "India"))
    tasks: List[Dict[str, Any]] = []
    if jurisdiction.lower() == "india":
        tasks += [
            {"agent": "IP Research", "domain": "IP", "question": "What current Indian IP provisions and official guidance are relevant to this product and its proposed claims?"},
            {"agent": "TK Research", "domain": "TK", "question": "Is there evidence that the claimed use/formulation may correspond to documented traditional knowledge, and what evidence would establish this?"},
            {"agent": "ABS Research", "domain": "ABS", "question": "Do the stated biological resources or traditional uses create a potential access-and-benefit-sharing issue under current Indian rules?"},
            {"agent": "Web Research", "domain": "REGULATORY", "question": f"What current Indian regulatory classification/guidance applies to a {ptype} for the stated purpose: {purpose}?"},
        ]
    else:
        tasks += [
            {"agent": "IP Research", "domain": "IP", "question": "What current international treaty/registry information is relevant to the requested IP issue?"},
            {"agent": "TK Research", "domain": "TK", "question": "What authoritative international TK instruments or databases are relevant?"},
            {"agent": "ABS Research", "domain": "ABS", "question": "What current CBD/Nagoya-related evidence is relevant to the stated resources and use?"},
            {"agent": "Web Research", "domain": "REGULATORY", "question": "What current official regulatory information is relevant in the selected international context?"},
        ]
    if tk in {"yes", "true", "1"} or any(x.lower() in purpose.lower() for x in ("traditional", "ayur", "herbal")):
        tasks.append({"agent": "TK Research", "domain": "TK", "question": "Check whether documented traditional use changes the evidence requirements; do not infer TK status without documentary support."})
    if ingredients:
        tasks.append({"agent": "ABS Research", "domain": "ABS", "question": f"Check authoritative sources for biological-resource relevance of: {', '.join(ingredients[:20])}. Do not infer ABS applicability from ingredient names alone."})
    return {"facts": {"product_type": ptype, "jurisdiction": jurisdiction, "ingredients": ingredients}, "tasks": tasks, "classification_rule": "Separate FACT, INFERENCE, RECOMMENDATION and UNCERTAINTY; never convert an inference into a legal conclusion."}


def annotate_evidence(item: Dict[str, Any], *, fact: str = "", inference: str = "", recommendation: str = "", uncertainty: str = "") -> Dict[str, Any]:
    return {**item, "fact": fact, "inference": inference, "recommendation": recommendation, "uncertainty": uncertainty}
