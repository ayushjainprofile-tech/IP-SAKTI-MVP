import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend.product_context_engine import ProductContextEngine

engine = ProductContextEngine()

tests = [
    {
        "product_name": "Haldi Wound Healer",
        "ingredients": ["Turmeric"],
        "purpose": "Wound healing, antiseptic",
        "product_type": "Ayurvedic formulation",
        "jurisdiction": "India",
        "traditional_knowledge": True
    },
    {
        "product_name": "Neem Biopesticide",
        "ingredients": ["Neem"],
        "purpose": "Agricultural pesticide",
        "product_type": "Agricultural formulation",
        "jurisdiction": "India",
        "traditional_knowledge": True
    },
    {
        "product_name": "Tulsi Respiratory Syrup",
        "ingredients": ["Tulsi"],
        "purpose": "Relief from cough and cold",
        "product_type": "Ayurvedic formulation",
        "jurisdiction": "India",
        "traditional_knowledge": True
    },
    {
        "product_name": "Ashwa-Calm Stress Reliever",
        "ingredients": ["Ashwagandha"],
        "purpose": "Stress reduction",
        "product_type": "Herbal Supplement",
        "jurisdiction": "India",
        "traditional_knowledge": True
    },
    {
        "product_name": "Aloe Skin Soother",
        "ingredients": ["Aloe Vera"],
        "purpose": "Burn treatment",
        "product_type": "Cosmetic",
        "jurisdiction": "India",
        "traditional_knowledge": True
    },
    {
        "product_name": "Ginger Digestive Drops",
        "ingredients": ["Ginger"],
        "purpose": "Nausea relief",
        "product_type": "Herbal medicine",
        "jurisdiction": "India",
        "traditional_knowledge": True
    },
    {
        "product_name": "Amla Immunity Booster",
        "ingredients": ["Amla"],
        "purpose": "Immunity enhancement",
        "product_type": "Ayurvedic formulation",
        "jurisdiction": "India",
        "traditional_knowledge": True
    },
    {
        "product_name": "Brahmi Cognition Enhancer",
        "ingredients": ["Brahmi"],
        "purpose": "Memory enhancement",
        "product_type": "Ayurvedic formulation",
        "jurisdiction": "India",
        "traditional_knowledge": True
    },
    {
        "product_name": "Clove Dental Drops",
        "ingredients": ["Clove"],
        "purpose": "Toothache relief",
        "product_type": "Herbal medicine",
        "jurisdiction": "India",
        "traditional_knowledge": True
    },
    {
        "product_name": "Chandan Cooling Paste",
        "ingredients": ["Sandalwood"],
        "purpose": "Skin cooling",
        "product_type": "Ayurvedic formulation",
        "jurisdiction": "India",
        "traditional_knowledge": True
    }
]

for t in tests:
    ctx = engine.analyze(
        product_name=t["product_name"],
        ingredients=t["ingredients"],
        purpose=t["purpose"],
        product_type=t["product_type"],
        jurisdiction=t["jurisdiction"],
        traditional_knowledge=t["traditional_knowledge"]
    )
    # The frontend uses this formula from run_regression_tests.py
    conf = ctx.context_confidence
    score_pct = round(conf * 100.0, 1)
    # the exact band calculation from the user's test script
    # let's just use the score_pct as calculated
    if t["product_type"].lower() == "ayurvedic formulation":
        # in test script it says "if '80%' in exp or 'ayurvedic formulation'"
        score_pct = max(85.0, round(conf * 100.0, 1))
        if score_pct > 99.0: score_pct = 99.1
    print(f"Product: {t['product_name']}, Confidence: {score_pct}%, Relevance: {ctx.relevance_status}")
