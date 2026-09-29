"""
Regression tests for the ingredient / cosmetic common-sense master prompt.

Every rule the product analysis must never break is a test here, so a
change that reintroduces a known mistake (a search hit scored as evidence,
a default score, an ordinary word treated as an ingredient) fails.

Run from the repo root:   python -m pytest tests/test_master_prompt.py -q
Web research is switched off so results depend only on the local data.
"""

import os
import sys

import pytest

os.environ["AGENTIC_AI_ENABLED"] = "false"
os.environ.pop("TAVILY_API_KEY", None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from product_context_engine import ProductContextEngine  # noqa: E402


# ---------------------------------------------------------------------------
# §3 / §4 / §15 / §16-19 — one class per submitted ingredient
# ---------------------------------------------------------------------------

EXPECTED_CLASS = {
    "VERIFIED_INGREDIENT": [
        "neem", "turmeric", "Neem powder", "Turmeric extract", "haldi",
        "Azadirachta indica", "नीम", "हल्दी पाउडर", "Aloe vera gel",
        "glycerin", "almond oil",
    ],
    "POSSIBLE_INGREDIENT": [
        "lavender", "shea butter", "jojoba oil", "beeswax", "mint", "salt",
        "oats", "zinc oxide", "fig",
    ],
    "UNKNOWN_TRADITIONAL_INGREDIENT": [
        "punarnava", "kutki", "Punarnava extract", "vidanga", "अपामार्ग",
    ],
    "NON_INGREDIENT_COMMON_WORD": [
        "latent", "Latent powder", "happy", "car", "product", "test", "blue",
        "beautiful", "government", "rights", "defect", "testing", "bottle",
        "machine", "factory", "temperature", "voltage", "claim", "patent",
        # everyday words whose ingredient sense is rare (§10)
        "may", "two", "three", "come", "treat", "produce", "lead", "refuse",
        "special", "dard",
    ],
    "FORM_WORD": ["powder", "extract", "oil", "paste", "liquid", "capsule", "tel", "churna"],
    "PRODUCT_TYPE": ["shampoo", "soap", "lipstick", "sunscreen", "face wash", "serum", "sabun"],
    "RANDOM_GARBAGE": ["asdfghjkl", "xyz123", "qwerty", "qwerty987", "123456", "fh a i"],
}


@pytest.fixture(scope="module")
def engine():
    return ProductContextEngine()


@pytest.mark.parametrize(
    "term,expected",
    [(term, cls) for cls, terms in EXPECTED_CLASS.items() for term in terms],
)
def test_ingredient_class(engine, term, expected):
    assert engine.classify_ingredient(term)["ingredient_class"] == expected


def test_invalid_classes_are_invalid(engine):
    for term in ["latent", "powder", "shampoo", "asdfghjkl"]:
        assert engine.classify_ingredient(term)["cosmetic_validity"] == "INVALID"


# ---------------------------------------------------------------------------
# API — §24 decision matrix, §21 no default score, §22 no score from search
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    import main
    return TestClient(main.app)


_RESPONSES = {}


def analyze(client, name, ingredients, purpose, product_type, tk="Not sure"):
    """POST /api/analyze once per case; several tests check the same response."""
    key = (name, tuple(ingredients), purpose, product_type, tk)
    if key not in _RESPONSES:
        _RESPONSES[key] = client.post("/api/analyze", json={
            "product_name": name,
            "ingredients": ingredients,
            "purpose": purpose,
            "product_type": product_type,
            "jurisdiction": "India",
            "based_on_traditional_knowledge": tk,
        })
    return _RESPONSES[key]


ZERO_OUT_OF_SCOPE = [
    ("Latent powder", ["Latent"], "Latent", "Cosmetic", "Yes"),
    ("Happy Cream", ["Happy", "Car"], "skin care", "Cosmetic", "Not sure"),
    ("Box Cream", ["Bottle", "Machine"], "skin care", "Cosmetic", "Not sure"),
    ("Shampoo X", ["Shampoo"], "hair care", "Cosmetic", "Not sure"),
    ("Just Powder", ["powder"], "skin care", "Cosmetic", "Not sure"),
    ("May Cream", ["may"], "skin care", "Cosmetic", "Not sure"),
    ("Lead Cream", ["lead"], "skin care", "Cosmetic", "Not sure"),
    ("Two Cream", ["two", "three"], "skin care", "Cosmetic", "Not sure"),
    ("Chilli Cream", ["Chilli"], "skin care", "Cosmetic", "Not sure"),
    ("Plastic Bottle", ["Plastic"], "storage", "Cosmetic", "Not sure"),
]


@pytest.mark.parametrize("case", ZERO_OUT_OF_SCOPE, ids=[c[0] for c in ZERO_OUT_OF_SCOPE])
def test_invalid_or_mismatched_is_zero_out_of_scope(client, case):
    data = analyze(client, *case).json()
    assert data["confidence"]["score"] == 0
    assert data["confidence"]["level"] == "OUT_OF_SCOPE"
    assert data["evidence"] == []


ZERO_NO_EVIDENCE = [
    # verified, but no corpus document mentions it (§24 row 2)
    ("Neem Soap", ["Neem"], "skin cleansing", "Cosmetic", "Not sure"),
    ("Turmeric Face Cream", ["Turmeric"], "skin glow", "Cosmetic", "No"),
    # plausible / traditional, no evidence (§24 row 4)
    ("Lavender Oil", ["Lavender"], "relaxation", "Cosmetic", "Not sure"),
    ("Punarnava Churna", ["Punarnava"], "kidney health", "Ayurvedic formulation", "Yes"),
    # a real word used in legal text ("subject to the provisions of")
    ("Provisions Pack", ["provisions"], "food", "Food", "Not sure"),
]


@pytest.mark.parametrize("case", ZERO_NO_EVIDENCE, ids=[c[0] for c in ZERO_NO_EVIDENCE])
def test_no_mentioning_evidence_is_zero(client, case):
    data = analyze(client, *case).json()
    assert data["confidence"]["score"] == 0
    assert data["evidence"] == []
    assert data["evidence_gate"]["relevant_evidence_count"] == 0


SCORED = [
    ("Aloe Gel", ["Aloe vera"], "skin soothing", "Cosmetic", "Not sure"),
    ("Ashwa Joint Relief", ["Ashwagandha", "Turmeric"], "Joint pain", "Ayurvedic formulation", "Yes"),
]


@pytest.mark.parametrize("case", SCORED, ids=[c[0] for c in SCORED])
def test_verified_with_mentioning_evidence_scores(client, case):
    data = analyze(client, *case).json()
    assert data["confidence"]["score"] > 0
    assert data["evidence"]


@pytest.mark.parametrize(
    "case", ZERO_OUT_OF_SCOPE + ZERO_NO_EVIDENCE + SCORED,
    ids=[c[0] for c in ZERO_OUT_OF_SCOPE + ZERO_NO_EVIDENCE + SCORED],
)
def test_every_shown_evidence_mentions_the_ingredient(client, case):
    """§9/§22: no evidence item without an entity match; no score without evidence."""
    data = analyze(client, *case).json()
    for item in data["evidence"]:
        assert item["entity_matches"], item["source"]
    if data["confidence"]["score"] > 0:
        assert data["evidence"], "positive score with no evidence (default score)"


def test_mixed_valid_and_invalid_ignores_invalid(client):
    """§9 (first spec): Neem + Latent → latent ignored, never evidence."""
    data = analyze(client, "Neem Latent Soap", ["Neem", "Latent"], "skin cleansing", "Cosmetic").json()
    ctx = data["product_context_engine"]["context"]
    assert ctx["relevance_status"] == "RELEVANT"
    assert "latent" in [t.lower() for t in ctx["ignored_terms"]]
    for item in data["evidence"]:
        assert "latent" not in item["entity_matches"]


def test_gibberish_is_rejected(client):
    assert analyze(client, "joi ds f", ["fh a i"], "dfd 9df p9", "Cosmetic").status_code == 422


# ---------------------------------------------------------------------------
# §10 — same word, different meaning
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gate():
    import main
    return main._matched_entity_terms


@pytest.mark.parametrize("text,term", [
    ("the Controller may refuse the application", "may"),
    ("which may lead to revocation of the patent", "lead"),
    ("subject to the provisions of this Act", "provisions"),
    ("registered as a geographical indication for gold jewellery", "gold"),
    ("a latent defect in the device", "latent"),
])
def test_other_meaning_is_not_evidence(gate, text, term):
    assert gate(text, [term]) == []


@pytest.mark.parametrize("text,term", [
    ("a composition comprising ginger, radish, celery and black seed", "ginger"),
    ("calendula officinallis, aloe vera and centellae asiatica as healing agent", "aloe vera"),
    ("an aqueous extract of gold bhasma for skin", "gold"),
])
def test_ingredient_meaning_is_evidence(gate, text, term):
    assert gate(text, [term]) == [term]
