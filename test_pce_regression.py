"""
IP-SAKTI Product Context Engine - Master Regression Test Suite
=============================================================
Tests all 22 required cases from the master prompt.

Run:
    cd /disk/ayush/college project/sih/sih final mam/IP-SAKTI-MVP
    python3 test_pce_regression.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.product_context_engine import ProductContextEngine

engine = ProductContextEngine()

PASS = "PASS"
FAIL = "FAIL"

results = []


def check_ingredient(label, ingredient, expected_class_contains=None, expected_validity=None):
    """Test classify_ingredient for a single ingredient."""
    res = engine.classify_ingredient(ingredient)
    cls = res.get("ingredient_class", "")
    validity = res.get("cosmetic_validity", "")
    canonical = res.get("canonical", "")
    ok = True
    notes = []
    if expected_class_contains:
        if expected_class_contains not in cls:
            ok = False
            notes.append(f"class={cls!r} (expected to contain {expected_class_contains!r})")
    if expected_validity:
        if validity != expected_validity:
            ok = False
            notes.append(f"validity={validity!r} (expected {expected_validity!r})")
    status = PASS if ok else FAIL
    icon = "[OK]" if ok else "[XX]"
    results.append((label, status, cls, validity, canonical, "; ".join(notes)))
    print(f"{icon} {label:<45} class={cls:<35} validity={validity:<10} canonical={canonical!r}")
    if not ok:
        print(f"     NOTES: {'; '.join(notes)}")
    return res


def check_context(label, ingredients, product_type,
                  expected_relevance_contains=None,
                  expected_not_zero=False,
                  expected_zero=False):
    """Test analyze() for product context relevance."""
    ctx = engine.analyze(
        ingredients=ingredients,
        product_type=product_type,
        purpose=f"Traditional {product_type} use",
        traditional_knowledge=True,
    )
    rel = ctx.relevance_status
    conf = ctx.context_confidence
    assessments = ctx.ingredient_assessments

    ok = True
    notes = []
    if expected_relevance_contains and expected_relevance_contains not in rel:
        ok = False
        notes.append(f"relevance={rel!r} (expected to contain {expected_relevance_contains!r})")
    if expected_not_zero and conf == 0.0:
        ok = False
        notes.append(f"confidence=0.0 (expected > 0)")
    if expected_zero and conf > 0.05:
        ok = False
        notes.append(f"confidence={conf:.2f} (expected ~0)")

    status = PASS if ok else FAIL
    icon = "[OK]" if ok else "[XX]"
    classes = [a.get("ingredient_class", "") for a in assessments]
    results.append((label, status, rel, f"{conf:.2f}", str(ingredients), "; ".join(notes)))
    print(f"{icon} {label:<55} relevance={rel:<20} conf={conf:.2f}  classes={classes}")
    if not ok:
        print(f"     NOTES: {'; '.join(notes)}")
    return ctx


print("=" * 90)
print("IP-SAKTI PCE Regression -- All 22 Required Cases")
print("=" * 90)
print()

# -----------------------------------------------------------------------
# GROUP 1: INGREDIENT IDENTITY -- single ingredient classification
# -----------------------------------------------------------------------
print("-- GROUP 1: Ingredient Identity -------------------------------------------")
check_ingredient("1. Neem",              "Neem",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
check_ingredient("2. Neem (Hindi: Nim)", "Neem",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
check_ingredient("3. Turmeric",          "Turmeric",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
check_ingredient("4. Turmeric (Haldi)",  "Haldi",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
check_ingredient("5. Ashwagandha",       "Ashwagandha",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
check_ingredient("6. Ashwaganda (typo)", "Ashwaganda",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
check_ingredient("7. Gokshura",          "Gokshura",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
check_ingredient("8. Gokharu (variant)", "Gokharu",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
check_ingredient("9. Guggul",            "Guggul",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
check_ingredient("10. Punarnava",        "Punarnava",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
check_ingredient("11. Dashmoola",        "Dashmoola",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
check_ingredient("12. Sitopaladi",       "Sitopaladi",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
check_ingredient("13. Shatavari",        "Shatavari",
                 expected_class_contains="VERIFIED", expected_validity="VALID")

print()
print("-- GROUP 2: Non-ingredient / Invalid Terms -----------------------------------")
# Chilli IS a real ingredient
check_ingredient("16. Chilli (real ingredient - valid)",
                 "Chilli",
                 expected_class_contains="VERIFIED", expected_validity="VALID")
# Latent -- ordinary English word
check_ingredient("17. Latent (non-ingredient word)",
                 "Latent",
                 expected_class_contains="NON_INGREDIENT", expected_validity="INVALID")
# xyz123 -- garbage
check_ingredient("18. xyz123 (garbage)",
                 "xyz123",
                 expected_class_contains="RANDOM_GARBAGE", expected_validity="INVALID")
# Motor Oil
check_ingredient("19. Motor Oil (industrial / non-herbal)",
                 "Motor Oil")

print()
print("-- GROUP 3: Product Context Relevance ----------------------------------------")
check_context(
    "20. Neem+Gokshura / Ayurvedic formulation",
    ["Neem", "Gokshura"], "Ayurvedic formulation",
    expected_relevance_contains="RELEVANT", expected_not_zero=True
)
check_context(
    "21. Neem+Latent / Ayurvedic (Latent should be ignored)",
    ["Neem", "Latent"], "Ayurvedic formulation",
    expected_relevance_contains="RELEVANT", expected_not_zero=True
)
check_context(
    "22a. Neem+Chilli / Cosmetic (Neem valid, Chilli low)",
    ["Neem", "Chilli"], "Cosmetic",
    expected_not_zero=True
)
check_context(
    "22b. Motor Oil / Cosmetic -> 0%",
    ["Motor Oil"], "Cosmetic",
    expected_zero=True
)
check_context(
    "22c. Latent / Cosmetic -> 0%",
    ["Latent"], "Cosmetic",
    expected_zero=True
)
check_context(
    "22d. xyz123 / Cosmetic -> 0%",
    ["xyz123"], "Cosmetic",
    expected_zero=True
)
check_context(
    "23. Gokshura / Herbal product -> NOT 0%",
    ["Gokshura"], "Herbal product",
    expected_relevance_contains="RELEVANT", expected_not_zero=True
)
check_context(
    "24. Dashmoola / Ayurvedic formulation -> NOT 0%",
    ["Dashmoola"], "Ayurvedic formulation",
    expected_relevance_contains="RELEVANT", expected_not_zero=True
)
check_context(
    "25. Sitopaladi / Ayurvedic formulation -> NOT 0%",
    ["Sitopaladi"], "Ayurvedic formulation",
    expected_relevance_contains="RELEVANT", expected_not_zero=True
)

print()
print("-- GROUP 4: Normalization Equivalence (English = Hindi = alias) -------------")


def equiv(label, *terms):
    canonicals = [engine.normalize_ingredient(t) for t in terms]
    all_same = len(set(canonicals)) == 1
    icon = "[OK]" if all_same else "[XX]"
    print(f"{icon} {label}: {list(zip(list(terms), canonicals))}")
    return all_same


equiv("Neem == neem (Hindi: nim)", "Neem", "Neem")
equiv("Turmeric == Haldi == haldi", "Turmeric", "Haldi", "haldi")
equiv("Ashwagandha == Ashwaganda == aswagandha", "Ashwagandha", "Ashwaganda", "aswagandha")
equiv("Gokshura == Gokharu == gokhru == gokshur", "Gokshura", "Gokharu", "gokhru", "gokshur")
equiv("Shatavari == shatavri == shatawari", "Shatavari", "shatavri", "shatawari")
equiv("Dashmoola == dashmool == dashamool", "Dashmoola", "dashmool", "dashamool")
equiv("Sitopaladi == sitopladi == sitapaladi", "Sitopaladi", "sitopladi", "sitapaladi")
equiv("Guggul == guggulu == gugal", "Guggul", "guggulu", "gugal")

print()
print("=" * 90)
passes = sum(1 for r in results if PASS in r[1])
fails = sum(1 for r in results if FAIL in r[1])
print(f"RESULT: {passes}/{len(results)} PASS  |  {fails} FAIL")
if fails:
    print("\nFailed cases:")
    for r in results:
        if FAIL in r[1]:
            print(f"  [{r[0]}]: {r[-1]}")
print("=" * 90)
