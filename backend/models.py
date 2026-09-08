from pydantic import BaseModel, Field
from typing import List, Optional


class ProductInput(BaseModel):
    product_name: str = Field(min_length=1)
    ingredients: List[str] = Field(default_factory=list)
    purpose: str = ""
    product_type: str = "Ayurvedic formulation"
    jurisdiction: str = "India"
    based_on_traditional_knowledge: Optional[str] = "Not sure"


class AnalyzeResponse(BaseModel):
    product: dict
    classification: dict
    domains: List[str]
    evidence: List[dict]
    reasoning: dict
    validation: dict
    confidence: dict
    action_plan: List[str]
