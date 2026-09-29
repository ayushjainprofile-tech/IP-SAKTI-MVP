"""
Product Context Engine
======================

Standalone, additive context analysis for product/ingredient-aware retrieval.

Core principle:
    INGREDIENT != PRODUCT != PRODUCT USE != EVIDENCE

This module classifies product context and retrieval relevance only.
It does not make medical, safety, efficacy, or legal conclusions.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence
import difflib
import json
import re


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ONTOLOGY_PATH = BASE_DIR / "data" / "ingredient_ontology.json"
DEFAULT_EXAMPLES_PATH = BASE_DIR / "data" / "product_context_examples.json"
# English dictionary words + words seen in the TK/IP/ABS corpus.
DEFAULT_VOCABULARY_PATH = BASE_DIR / "data" / "vocabulary.txt"

# Ayurvedic / Hinglish product words a dictionary will not know.
DEFAULT_INDIAN_WORDS_PATH = BASE_DIR / "data" / "indian_product_words.txt"
# Words that name a plant, food, substance or material (WordNet nouns under
# plant / food / substance / material / chemical ...), used to tell an
# ingredient missing from the ontology ("lavender") from an ordinary word
# that is not an ingredient at all ("latent").
DEFAULT_INGREDIENT_WORDS_PATH = BASE_DIR / "data" / "ingredient_words.txt"
# Indian herb / spice names (a subset of indian_product_words.txt); an unknown
# name found here is a traditional ingredient, not an ordinary word.
DEFAULT_INDIAN_INGREDIENTS_PATH = BASE_DIR / "data" / "indian_ingredient_words.txt"

# Form/quality words that do not identify an ingredient on their own.
INGREDIENT_FORM_WORDS = {
    "powder", "extract", "oil", "cream", "gel", "juice", "paste", "lotion",
    "serum", "soap", "capsule", "tablet", "syrup", "tea", "water", "milk",
    "seed", "root", "leaf", "bark", "flour", "spice", "butter", "essential",
    "pure", "organic", "natural", "dried", "fresh", "raw", "liquid",
    "solution", "resin", "distillate", "concentrate", "granules", "tincture",
    # Ayurvedic / Hindi forms
    "tel", "churna", "choorna", "vati", "bhasma", "taila", "tailam", "ghrita",
    "lepa", "lep", "kwath", "kadha", "arishta", "asava", "avaleha", "rasayana",
}

# Product types, not ingredients ("shampoo" submitted as an ingredient).
PRODUCT_TYPE = "PRODUCT_TYPE"  # a product ("shampoo"), not an ingredient
PRODUCT_TYPE_WORDS = {
    "shampoo", "soap", "lipstick", "sunscreen", "sunblock", "face wash", "facewash",
    "body wash", "hand wash", "cleanser", "moisturizer", "moisturiser", "toner",
    "conditioner", "deodorant", "perfume", "kajal", "kohl", "toothpaste",
    "mouthwash", "scrub", "face mask", "mask", "lip balm", "balm", "foundation",
    "mascara", "eyeliner", "nail polish", "hair dye", "hair oil", "face cream",
    "cream", "lotion", "serum", "gel", "sabun", "ubtan", "cosmetic", "cosmetics",
}

# Ingredient classes (one per submitted ingredient).
VERIFIED_INGREDIENT = "VERIFIED_INGREDIENT"                  # in the ontology
POSSIBLE_INGREDIENT = "POSSIBLE_INGREDIENT"                  # names a plant/food/substance, not in ontology
UNKNOWN_TRADITIONAL_INGREDIENT = "UNKNOWN_TRADITIONAL_INGREDIENT"  # not ordinary English; likely a regional herb
NON_INGREDIENT_COMMON_WORD = "NON_INGREDIENT_COMMON_WORD"    # ordinary word, not a substance
FORM_WORD = "FORM_WORD"                                      # only a form ("powder") with no ingredient
RANDOM_GARBAGE = "RANDOM_GARBAGE"                            # keyboard mash / digits / no real word

# How sure the engine is that a term is the ingredient it resolved to (0-1).
FUZZY_MATCH_CUTOFF = 0.75          # "ashwaganda" ~ "ashwagandha" = 0.95, "gokharu" ~ "gokshura" = 0.77
IDENTITY_CONFIDENCE = {
    "exact": 1.0,                 # canonical / alias / scientific / Hindi name
    "POSSIBLE_INGREDIENT": 0.65,  # names a plant / food / substance, not in ontology
    "UNKNOWN_TRADITIONAL_INGREDIENT": 0.65,
    "NON_INGREDIENT_COMMON_WORD": 0.02, # Unrelated words like "latent" should have a tiny score, not 0
}

INVALID_INGREDIENT_CLASSES = {NON_INGREDIENT_COMMON_WORD, FORM_WORD, RANDOM_GARBAGE, PRODUCT_TYPE}

# cosmetic/product validity of each class (spec: VALID / PLAUSIBLE / UNKNOWN / INVALID).
CLASS_VALIDITY = {
    "VERIFIED_INGREDIENT": "VALID",
    "POSSIBLE_INGREDIENT": "PLAUSIBLE",
    "UNKNOWN_TRADITIONAL_INGREDIENT": "UNKNOWN",
    "NON_INGREDIENT_COMMON_WORD": "INVALID",
    "FORM_WORD": "INVALID",
    "RANDOM_GARBAGE": "INVALID",
    "PRODUCT_TYPE": "INVALID",
}
PLAUSIBLE_UNKNOWN_CLASSES = {POSSIBLE_INGREDIENT, UNKNOWN_TRADITIONAL_INGREDIENT}

_KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890")


PRODUCT_TAXONOMY = {
    "FOOD": {
        "spice", "powder", "flour", "tea", "beverage", "edible oil",
        "food preparation", "raw plant material", "processed food",
        "snack", "nutraceutical/food supplement",
    },
    "COSMETIC": {
        "cream", "lotion", "serum", "oil", "shampoo", "soap",
        "face mask", "hair product", "skin product", "gel",
    },
    "AYURVEDA / AYUSH": {
        "classical medicine", "patent/proprietary medicine",
        "traditional formulation", "topical Ayurvedic preparation",
        "oral Ayurvedic preparation",
    },
    "HEALTH / SUPPLEMENT": {
        "capsule", "tablet", "extract", "powder", "syrup", "supplement",
    },
    "RESEARCH / INDUSTRIAL": {
        "extract", "purified compound", "raw biological material",
        "laboratory material", "industrial ingredient",
    },
    "AGRICULTURAL": {
        "seed", "plant variety", "cultivation material", "agricultural product",
        "agricultural preparation",
    },
    "UNKNOWN": {"unknown/ambiguous"},
}

CATEGORY_ALIASES = {
    "food": "FOOD",
    "food/spice": "FOOD",
    "spice": "FOOD",
    "cosmetic": "COSMETIC",
    "beauty": "COSMETIC",
    "ayush": "AYURVEDA / AYUSH",
    "ayurveda": "AYURVEDA / AYUSH",
    "ayurvedic formulation": "AYURVEDA / AYUSH",
    "herbal product": "AYURVEDA / AYUSH",
    "herbal": "AYURVEDA / AYUSH",
    "supplement": "HEALTH / SUPPLEMENT",
    "health": "HEALTH / SUPPLEMENT",
    "research": "RESEARCH / INDUSTRIAL",
    "industrial": "RESEARCH / INDUSTRIAL",
    "agricultural": "AGRICULTURAL",
    "agriculture": "AGRICULTURAL",
}

USE_PATTERNS = {
    "food": [r"\bcook(?:ing)?\b", r"\bfood\b", r"\bedible\b", r"\bspice\b", r"\bmasala\b", r"\brecipe\b"],
    "cosmetic": [r"\bface\b", r"\bskin\b", r"\bhair\b", r"\btopical\b", r"\bcosmetic\b", r"\bcream\b", r"\blotion\b", r"\bserum\b", r"\bmask\b", r"\bshampoo\b", r"\bsoap\b"],
    "beverage": [r"\btea\b", r"\bjuice\b", r"\bdrink\b", r"\bbeverage\b", r"\bmilk\b"],
    "supplement": [r"\bcapsule\b", r"\btablet\b", r"\bsupplement\b", r"\bsyrup\b", r"\bingestible\b"],
    "ayush": [r"\bayurvedic\b", r"\bayush\b", r"\bclassical formulation\b", r"\btraditional formulation\b"],
    "agricultural": [r"\bseed\b", r"\bcultivat(?:e|ion)\b", r"\bpesticide\b", r"\bagricultur(?:e|al)\b", r"\bcrop\b"],
    "research": [r"\bresearch\b", r"\blaboratory\b", r"\blab\b", r"\bpurified compound\b", r"\bexperimental\b"],
    "industrial": [r"\bindustrial\b", r"\bmanufacturing\b", r"\bindustrial ingredient\b"],
    "traditional": [r"\btraditional\b", r"\bfolk\b", r"\bhome remedy\b", r"\btraditional knowledge\b"],
}

FORM_PATTERNS = [
    "face cream", "hair oil", "coconut oil", "mustard oil", "sesame oil",
    "olive oil", "capsule", "tablet", "syrup", "cream", "lotion", "serum",
    "shampoo", "soap", "face mask", "gel", "juice", "tea", "powder",
    "extract", "oil", "seed", "root", "leaf", "bark", "paste", "milk",
    "water", "snack", "flour", "beverage", "spice",
]

AMBIGUOUS_ONLY_PHRASES = {
    "chilli powder", "chili powder", "turmeric powder", "ginger powder",
    "neem powder", "moringa powder", "black pepper powder", "cinnamon powder",
    "garlic powder", "coconut oil", "sesame oil", "mustard oil", "ginger extract",
    "aloe vera gel", "aloe vera juice",
}

@dataclass
class ProductContext:
    product_name: Optional[str] = None
    normalized_product_name: str = ""
    ingredients: list[str] = field(default_factory=list)
    normalized_ingredients: list[str] = field(default_factory=list)
    scientific_names: list[str] = field(default_factory=list)
    product_form: Optional[str] = None
    intended_use: Optional[str] = None
    product_category: str = "UNKNOWN"
    jurisdiction: Optional[str] = None
    traditional_knowledge: Optional[bool] = None
    possible_contexts: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    requires_clarification: bool = False
    context_confidence: float = 0.0
    # RELEVANT / LOW_CONTEXT / IRRELEVANT / UNDETERMINED: does the product make sense
    # for its ingredients and stated category?
    relevance_status: str = "UNDETERMINED"
    relevance_reasons: list[str] = field(default_factory=list)
    # One entry per ingredient: identity, ingredient_class, ontology_match,
    # common_sense_check, reason.
    ingredient_assessments: list[dict[str, Any]] = field(default_factory=list)
    # Submitted terms that are not ingredients and were ignored.
    ignored_terms: list[str] = field(default_factory=list)
    retrieval_queries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@lru_cache(maxsize=1)
def _load_vocabulary(path: str) -> frozenset[str]:
    words: set[str] = set()
    for pattern_words in (PRODUCT_TAXONOMY.values(), [FORM_PATTERNS]):
        for group in pattern_words:
            for phrase in group:
                words.update(re.findall(r"[a-z]{3,}", phrase.lower()))
    for vocab_path in (Path(path), DEFAULT_INDIAN_WORDS_PATH):
        if vocab_path.exists():
            with vocab_path.open("r", encoding="utf-8") as f:
                words.update(line.strip().lower() for line in f if line.strip())
    return frozenset(words)


@lru_cache(maxsize=1)
def _load_ingredient_words(path: str) -> frozenset[str]:
    words_path = Path(path)
    if not words_path.exists():
        return frozenset()
    with words_path.open("r", encoding="utf-8") as f:
        return frozenset(line.strip().lower() for line in f if line.strip())


class ProductContextEngine:
    """Data-driven product-context analyzer."""

    def __init__(
        self,
        ontology_path: str | Path = DEFAULT_ONTOLOGY_PATH,
        examples_path: str | Path = DEFAULT_EXAMPLES_PATH,
    ) -> None:
        self.ontology_path = Path(ontology_path)
        self.examples_path = Path(examples_path)
        self.ontology = self._load_json(self.ontology_path)
        self.examples = self._load_json(self.examples_path) if self.examples_path.exists() else []

        self.vocabulary = _load_vocabulary(str(DEFAULT_VOCABULARY_PATH))
        self.ingredient_words = _load_ingredient_words(str(DEFAULT_INGREDIENT_WORDS_PATH))
        self.indian_ingredients = _load_ingredient_words(str(DEFAULT_INDIAN_INGREDIENTS_PATH))

        self._alias_to_canonical: dict[str, str] = {}
        self._scientific_to_canonical: dict[str, str] = {}
        for canonical, record in self.ontology.items():
            for value in [canonical, *record.get("common_names", []), *record.get("regional_names", [])]:
                self._alias_to_canonical[self._norm(value)] = canonical
            for value in record.get("scientific_names", []):
                self._scientific_to_canonical[self._norm(value)] = canonical

    def has_known_words(self, *texts: Any) -> bool:
        """True if any word in the input is a real word or known ingredient.

        Non-Latin script (e.g. Hindi) cannot be checked and counts as known.
        """
        raw = " ".join(str(x) for x in texts if x)
        if re.search(r"[^\x00-\x7f]", raw):
            return True
        tokens = re.findall(r"[a-z]{3,}", self._norm(raw))
        return any(
            t in self.vocabulary or t in self._alias_to_canonical for t in tokens
        )

    def _is_ingredient_word(self, token: str) -> bool:
        if token in self.ingredient_words or token in self._alias_to_canonical:
            return True
        # Plural forms: "almonds", "oats" -> "almond", "oat".
        return token.endswith("s") and token[:-1] in self.ingredient_words

    @staticmethod
    def _looks_random(token: str) -> bool:
        if len(token) < 3 or not re.search(r"[aeiou]", token):
            return True
        if re.search(r"[bcdfghjklmnpqrstvwxz]{5,}", token) or re.search(r"(.)\1\1", token):
            return True
        return any(
            len(token) >= 4 and token[k:k + 4] in row
            for row in _KEYBOARD_ROWS for k in range(len(token) - 3)
        )

    def classify_ingredient(self, name: str) -> dict[str, Any]:
        """Classify one submitted ingredient (common-sense gate).

        Order: ontology (verified) -> plant/food/substance/material word
        (possible) -> ordinary English word (not an ingredient) -> keyboard
        mash (garbage) -> anything else is treated as an unknown regional /
        traditional name and is NOT blocked. A word appearing in the legal
        corpus never makes it an ingredient.
        """
        raw = str(name or "")
        norm = self._norm(raw)
        canonical = self.normalize_ingredient(raw)

        def result(identity, cls, check, reason, canonical_name=None, confidence=None, match_type=None):
            if confidence is None:
                confidence = (
                    IDENTITY_CONFIDENCE["exact"] if cls == VERIFIED_INGREDIENT
                    else IDENTITY_CONFIDENCE.get(cls, 0.0)
                )
            return {
                "input": raw,
                "ingredient_identity": identity,
                "canonical": canonical_name,
                "ingredient_class": cls,
                "cosmetic_validity": CLASS_VALIDITY[cls],
                "ontology_match": canonical_name is not None,
                "match_type": match_type or ("exact" if cls == VERIFIED_INGREDIENT else cls.lower()),
                "identity_confidence": round(confidence, 2),
                "common_sense_check": check,
                "reason": reason,
            }

        if canonical in self.ontology:
            return result(canonical, VERIFIED_INGREDIENT, "passed",
                          f"'{canonical}' is in the ingredient ontology.", canonical)
        inner = self._aliases_in(raw)
        if inner:
            return result(inner[0], VERIFIED_INGREDIENT, "passed",
                          f"'{raw}' contains the known ingredient '{inner[0]}'.", inner[0])

        translation_map = {
            "नीम": "neem",
            "neem": "neem",
            "हल्दी": "turmeric",
            "haldi": "turmeric",
            "अश्वगंधा": "ashwagandha",
            "ashwaganda": "ashwagandha",
            "गोखरू": "gokshura",
            "gokharu": "gokshura",
            "गुग्गुल": "guggul",
            "shatavri": "shatavari"
        }
        if norm in translation_map:
            translated_canonical = self.normalize_ingredient(translation_map[norm])
            return result(translated_canonical, VERIFIED_INGREDIENT, "passed",
                          f"'{raw}' translates to known ingredient '{translated_canonical}'.", translated_canonical, match_type="translation")

        fuzzy = self._fuzzy_canonical(raw)
        if fuzzy:
            name, ratio, alias = fuzzy
            return result(name, VERIFIED_INGREDIENT, "passed",
                          f"'{raw}' closely matches '{alias}' ({round(ratio * 100)}% similar), "
                          f"resolved to '{name}'.", name, confidence=ratio, match_type="fuzzy")

        if re.search(r"[\u0900-\u097f]", norm):
            # No Hindi dictionary to judge by: stay conservative (UNKNOWN).
            return result(norm, UNKNOWN_TRADITIONAL_INGREDIENT, "uncertain",
                          f"'{raw}' (Hindi script) is not in the ingredient ontology; "
                          "its identity could not be verified.")
        if re.search(r"\d", norm):
            return result(norm, RANDOM_GARBAGE, "failed",
                          f"'{raw}' is not a recognisable ingredient name.")
        if norm in PRODUCT_TYPE_WORDS:
            return result(norm, PRODUCT_TYPE, "failed",
                          f"'{raw}' is a product type, not an ingredient.")
        tokens = re.findall(r"[a-z]+", norm)
        core = [t for t in tokens if t not in INGREDIENT_FORM_WORDS]
        identity = " ".join(core) or norm
        if tokens and not core:
            return result(norm, FORM_WORD, "failed",
                          f"'{raw}' is only a product form, not an ingredient.")
        if not core:
            return result(norm, RANDOM_GARBAGE, "failed",
                          f"'{raw}' is not a recognisable ingredient name.")
        if identity in PRODUCT_TYPE_WORDS:
            return result(identity, PRODUCT_TYPE, "failed",
                          f"'{raw}' is a product type, not an ingredient.")
        if any(t in self.indian_ingredients for t in core):
            return result(identity, UNKNOWN_TRADITIONAL_INGREDIENT, "uncertain",
                          f"'{identity}' is a traditional / regional ingredient name "
                          "not in the ingredient ontology.")
        if all(self._looks_random(t) for t in core if t not in self.ingredient_words):
            if not any(t in self.ingredient_words for t in core):
                return result(identity, RANDOM_GARBAGE, "failed",
                              f"'{raw}' is not a recognisable ingredient name.")

        if identity in self.ingredient_words or norm in self.ingredient_words or any(
            self._is_ingredient_word(t) for t in core if len(t) >= 3
        ):
            return result(identity, POSSIBLE_INGREDIENT, "passed",
                          f"'{identity}' names a plant, food, substance or material, "
                          "but is not in the ingredient ontology.")
        if all(t in self.vocabulary for t in core if len(t) >= 3) and any(len(t) >= 3 for t in core):
            return result(identity, NON_INGREDIENT_COMMON_WORD, "failed",
                          f"'{identity}' is an ordinary word, not a plant, herb, food or material.")
        unknown = [t for t in core if t not in self.vocabulary]
        if all(self._looks_random(t) for t in unknown):
            return result(identity, RANDOM_GARBAGE, "failed",
                          f"'{raw}' is not a recognisable ingredient name.")
        return result(identity, UNKNOWN_TRADITIONAL_INGREDIENT, "uncertain",
                      f"'{identity}' is not in the ontology and not an ordinary English word; "
                      "it may be a regional or traditional ingredient name.")

    @staticmethod
    def _load_json(path: Path) -> Any:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _norm(value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip().lower()
        text = re.sub(r"[\u2018\u2019\u201c\u201d]", "'", text)
        text = re.sub(r"[^a-z0-9\u0900-\u097f\s\-/]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def normalize_ingredient(self, value: str) -> str:
        norm = self._norm(value)
        if norm in self._alias_to_canonical:
            return self._alias_to_canonical[norm]
        if norm in self._scientific_to_canonical:
            return self._scientific_to_canonical[norm]
        return norm

    def _aliases_in(self, text: str) -> list[str]:
        """Canonical ingredients whose name/alias/scientific name occurs in text."""
        norm_text = self._norm(text)
        names = {**self._scientific_to_canonical, **self._alias_to_canonical}
        found: list[str] = []
        # Longest aliases first prevents "tea" from firing before "green tea".
        for alias in sorted(names, key=len, reverse=True):
            if len(alias) < 3:
                continue
            if re.search(rf"(?<![a-z0-9\u0900-\u097f]){re.escape(alias)}(?![a-z0-9\u0900-\u097f])", norm_text):
                found.append(names[alias])
        return found

    def _fuzzy_canonical(self, raw: str):
        """Closest ontology name for a misspelling ("Ashwaganda", "Turmaric",
        "Shatavri"), as (canonical, similarity, matched_name), or None.
        Form words are ignored; only names of 4+ characters are compared."""
        norm = self._norm(raw)
        tokens = norm.split()
        core = " ".join(t for t in tokens if t not in INGREDIENT_FORM_WORDS) or norm
        if len(core) < 4:
            return None
        names = {**self._scientific_to_canonical, **self._alias_to_canonical}
        candidates = [a for a in names if len(a) >= 4]
        best = None
        for probe in dict.fromkeys([core, *core.split()]):
            if len(probe) < 4:
                continue
            for alias in difflib.get_close_matches(probe, candidates, n=1, cutoff=FUZZY_MATCH_CUTOFF):
                ratio = difflib.SequenceMatcher(None, probe, alias).ratio()
                if not best or ratio > best[1]:
                    best = (names[alias], ratio, alias)
        return best

    def resolve_ingredients(self, ingredients: Sequence[str]) -> list[str]:
        """Canonical names for user-entered ingredients ("Aloe vera gel" -> "aloe vera")."""
        return self._find_ingredients("", ingredients)

    def _find_ingredients(self, text: str, explicit: Sequence[str] | None) -> list[str]:
        found: list[str] = []
        for raw in explicit or []:
            if not self._norm(raw):
                continue
            canonical = self.normalize_ingredient(raw)
            if canonical in self.ontology:
                found.append(canonical)
                continue
            # "Turmeric extract", "Aloe vera gel": the ingredient plus a form.
            inner = self._aliases_in(raw)
            if not inner:
                fuzzy = self._fuzzy_canonical(raw)  # "Ashwaganda" -> ashwagandha
                inner = [fuzzy[0]] if fuzzy else []
            found.extend(inner or [canonical])
        found.extend(self._aliases_in(text))
        # Preserve order, remove duplicates.
        return list(dict.fromkeys(found))

    @staticmethod
    def _match_use(text: str) -> list[str]:
        norm = ProductContextEngine._norm(text)
        matches = []
        for use, patterns in USE_PATTERNS.items():
            if any(re.search(p, norm) for p in patterns):
                matches.append(use)
        return matches

    @staticmethod
    def _infer_form(text: str, product_type: str | None) -> Optional[str]:
        norm = ProductContextEngine._norm(text)
        for form in sorted(FORM_PATTERNS, key=len, reverse=True):
            if re.search(rf"(?<![a-z0-9]){re.escape(form)}(?![a-z0-9])", norm):
                return form.split()[-1] if " " in form else form
        return product_type.strip().lower() if product_type else None

    @staticmethod
    def _category_from_inputs(product_type: str | None, uses: Iterable[str]) -> str:
        use_set = set(uses)
        if "research" in use_set or "industrial" in use_set:
            return "RESEARCH / INDUSTRIAL"
        if product_type:
            p = ProductContextEngine._norm(product_type)
            if p in CATEGORY_ALIASES:
                return CATEGORY_ALIASES[p]
            for category, forms in PRODUCT_TAXONOMY.items():
                if p in {ProductContextEngine._norm(x) for x in forms}:
                    return category
        if "cosmetic" in use_set:
            return "COSMETIC"
        if "agricultural" in use_set:
            return "AGRICULTURAL"
        if "research" in use_set or "industrial" in use_set:
            return "RESEARCH / INDUSTRIAL"
        if "ayush" in use_set or "traditional" in use_set:
            return "AYURVEDA / AYUSH"
        if "supplement" in use_set:
            return "HEALTH / SUPPLEMENT"
        if "beverage" in use_set or "food" in use_set:
            return "FOOD"
        return "UNKNOWN"

    def _assess_relevance(
        self,
        ingredients: Sequence[str],
        category: str,
        compatible_contexts: set[str] | None,
    ) -> tuple[str, list[str]]:
        """Decide whether the ingredients plausibly belong to the product category.

        IRRELEVANT only on a clear signal from the ontology; ingredients the
        ontology does not know leave the result UNDETERMINED.
        """
        known = [x for x in ingredients if x in self.ontology]
        assessments = [self.classify_ingredient(x) for x in ingredients if x not in self.ontology]
        invalid = [a for a in assessments if a["ingredient_class"] in INVALID_INGREDIENT_CLASSES]
        plausible = [a for a in assessments if a["ingredient_class"] in PLAUSIBLE_UNKNOWN_CLASSES]
        non_ingredient_reasons = [
            f"Ignored term: {a['reason']}" for a in invalid
        ]
        if not known:
            if plausible:
                return "UNDETERMINED", [a["reason"] for a in plausible] + non_ingredient_reasons
            if invalid:
                return "IRRELEVANT", [a["reason"] for a in invalid]
            return "UNDETERMINED", ["No ingredient was given."]

        out_of_scope = [x for x in known if self.ontology[x].get("in_scope") is False]
        known = [x for x in known if x not in out_of_scope]
        if not known:
            return "IRRELEVANT", [
                f"'{x}' is a synthetic/industrial material, outside the "
                "Ayurveda/AYUSH/TK/IP scope." for x in out_of_scope
            ]

        if not compatible_contexts:
            return "UNDETERMINED", [f"Product category '{category}' could not be checked against ingredient contexts."]

        matching, mismatched = [], []
        for x in known:
            contexts = set(self.ontology[x].get("common_product_contexts", []))
            (matching if contexts & compatible_contexts else mismatched).append(x)

        if matching:
            return "RELEVANT", [
                f"'{x}' is commonly used in {category} products." for x in matching
            ] + [
                f"Note: '{x}' is not a known {category} ingredient (known uses: "
                f"{', '.join(self.ontology[x].get('common_product_contexts', []))})."
                for x in mismatched
            ] + non_ingredient_reasons
        # A real ingredient in an unusual product type is low relevance, not
        # an invalid input: it scores low instead of 0%.
        return "LOW_CONTEXT", [
            f"'{x}' is a valid ingredient but not a typical {category} ingredient "
            f"(known uses: {', '.join(self.ontology[x].get('common_product_contexts', []))})."
            for x in mismatched
        ] + non_ingredient_reasons

    def analyze(
        self,
        product_name: str | None = None,
        ingredients: Sequence[str] | None = None,
        purpose: str | None = None,
        product_type: str | None = None,
        jurisdiction: str | None = None,
        traditional_knowledge: bool | None = None,
    ) -> ProductContext:
        # The API sends the form answer as text ("Yes" / "No" / "Not sure").
        if isinstance(traditional_knowledge, str):
            answer = self._norm(traditional_knowledge)
            traditional_knowledge = (
                True if answer in {"yes", "true", "y", "1"}
                else False if answer in {"no", "false", "n", "0"}
                else None
            )
        combined = " ".join(
            x for x in [product_name or "", purpose or "", product_type or ""]
            if x
        )
        normalized_product = self._norm(product_name or combined)

        # ─────────────────────────────────────────────────────────────────
        # ENTITY RESOLUTION GATE (Rules 1, 13, 18, 20, 25)
        # Classify EVERY submitted ingredient BEFORE resolving ontology IDs.
        # Invalid classes (ordinary words, form words, garbage, product
        # types) are rejected here and can NEVER enter the evidence or
        # scoring pipeline.
        # ─────────────────────────────────────────────────────────────────
        raw_ingredients = list(ingredients or [])
        ingredient_assessments_all: list[dict] = [
            self.classify_ingredient(x) for x in raw_ingredients
        ]
        valid_raw_ingredients = [
            raw_ingredients[i]
            for i, a in enumerate(ingredient_assessments_all)
            if a["ingredient_class"] not in INVALID_INGREDIENT_CLASSES
        ]
        ignored_terms = [
            raw_ingredients[i]
            for i, a in enumerate(ingredient_assessments_all)
            if a["ingredient_class"] in INVALID_INGREDIENT_CLASSES
        ]
        # Hard gate: if every submitted ingredient is invalid, reject all.
        all_invalid = bool(raw_ingredients) and not valid_raw_ingredients

        ingredient_list = self._find_ingredients(combined, valid_raw_ingredients)
        scientific_names: list[str] = []
        possible_contexts: list[str] = []
        for canonical in ingredient_list:
            record = self.ontology.get(canonical, {})
            scientific_names.extend(record.get("scientific_names", []))
            possible_contexts.extend(record.get("common_product_contexts", []))
        scientific_names = list(dict.fromkeys(scientific_names))
        possible_contexts = list(dict.fromkeys(possible_contexts))

        uses = self._match_use(combined)
        form = self._infer_form(combined, product_type)
        category = self._category_from_inputs(product_type, uses)

        # Strong explicit category/use signals narrow the ontology contexts.
        category_map = {
            "FOOD": {"food/spice", "food", "beverage"},
            "COSMETIC": {"cosmetic"},
            "AYURVEDA / AYUSH": {"ayush", "traditional knowledge"},
            "HEALTH / SUPPLEMENT": {"supplement"},
            "AGRICULTURAL": {"agricultural"},
            "RESEARCH / INDUSTRIAL": {"research", "industrial"},
        }
        relevance_status, relevance_reasons = self._assess_relevance(
            ingredient_list, category, category_map.get(category)
        )
        # If all submitted ingredients were invalid ordinary/form/garbage
        # words, override relevance to IRRELEVANT regardless of category.
        if all_invalid:
            relevance_status = "IRRELEVANT"
            invalid_reasons = [
                ingredient_assessments_all[i]["reason"]
                for i, a in enumerate(ingredient_assessments_all)
                if a["ingredient_class"] in INVALID_INGREDIENT_CLASSES
            ]
            relevance_reasons = invalid_reasons or [
                "All submitted ingredients were rejected as non-ingredient terms."
            ]
        ingredient_assessments = ingredient_assessments_all
        compatible = category_map.get(category)
        for a in ingredient_assessments:
            record = self.ontology.get(a.get("canonical")) or {}
            if a["ingredient_class"] != VERIFIED_INGREDIENT or not compatible:
                a["context_fit"] = None           # cannot be checked
            elif record.get("in_scope") is False:
                a["context_fit"] = "out_of_scope"
            else:
                contexts = set(record.get("common_product_contexts", []))
                a["context_fit"] = "fits" if contexts & compatible else "mismatch"

        if category in category_map:
            narrowed = [x for x in possible_contexts if x in category_map[category]]
            if narrowed:
                possible_contexts = narrowed

        ambiguities: list[str] = []
        explicit_purpose = bool(purpose and self._norm(purpose))
        explicit_type = bool(product_type and self._norm(product_type))
        explicit_use_signal = bool(uses)
        is_bare_ambiguous = (
            bool(ingredient_list)
            and not explicit_purpose
            and not explicit_type
            and not explicit_use_signal
            and self._norm(product_name) in AMBIGUOUS_ONLY_PHRASES
        )
        if is_bare_ambiguous:
            ambiguities.append("intended_use_not_specified")
            if "food/spice" in possible_contexts:
                possible_contexts = ["food/spice", "traditional knowledge", "other preparation"]
            else:
                possible_contexts = ["food/spice", "traditional knowledge", "other preparation"]
        known_ingredients = [x for x in ingredient_list if x in self.ontology]
        # Nothing recognisable: no known ingredient and not a single real
        # word (e.g. "uoi 9 f"). Form/type/jurisdiction alone mean nothing.
        unrecognized_input = not known_ingredients and not self.has_known_words(
            product_name, purpose, *(ingredients or [])
        )
        if not ingredient_list:
            ambiguities.append("ingredient_not_resolved")
        elif not known_ingredients:
            ambiguities.append("ingredient_not_in_ontology")
        if unrecognized_input:
            ambiguities.append("input_not_recognized")
        if not form:
            ambiguities.append("product_form_not_resolved")
        if category == "UNKNOWN":
            ambiguities.append("product_category_not_resolved")

        # Transparent heuristic confidence: ingredient match alone is deliberately weak.
        score = 0.0
        signals = 0
        if known_ingredients:
            score += 0.15
            signals += 1
        if form:
            score += 0.20
            signals += 1
        if explicit_use_signal:
            score += 0.25
            signals += 1
        if explicit_type:
            score += 0.15
            signals += 1
        if category != "UNKNOWN":
            score += 0.10
            signals += 1
        if scientific_names:
            score += 0.05
            signals += 1
        if jurisdiction:
            score += 0.05
            signals += 1
        if traditional_knowledge is not None:
            score += 0.05
            signals += 1

        # Known example/context match adds a small contextual signal only.
        if normalized_product:
            norm_words = set(normalized_product.split())
            for ex in self.examples:
                ex_text = self._norm(ex.get("text", ""))
                if ex_text and ex_text == normalized_product:
                    score += 0.05
                    break

        score = min(0.99, round(score, 3))
        if is_bare_ambiguous:
            score = min(score, 0.35)
        if unrecognized_input:
            score = min(score, 0.20)
            relevance_reasons = relevance_reasons + [
                "The product name, ingredients and intended use contain no "
                "recognisable word or ingredient; please enter real "
                "ingredient names and a clear intended use."
            ]
        # Hard score gate (Rules 20, 25): IRRELEVANT or all_invalid → 0%
        if relevance_status == "IRRELEVANT" or all_invalid:
            score = 0.0

        requires_clarification = is_bare_ambiguous or unrecognized_input or (
            not ingredient_list and not explicit_type and not explicit_use_signal
        )

        context = ProductContext(
            product_name=product_name,
            normalized_product_name=normalized_product,
            ingredients=list(ingredients or []),
            normalized_ingredients=ingredient_list,
            scientific_names=scientific_names,
            product_form=form,
            intended_use=purpose,
            product_category=category,
            jurisdiction=jurisdiction,
            traditional_knowledge=traditional_knowledge,
            possible_contexts=possible_contexts,
            ambiguities=ambiguities,
            requires_clarification=requires_clarification,
            context_confidence=score,
            relevance_status=relevance_status,
            relevance_reasons=relevance_reasons,
            ingredient_assessments=ingredient_assessments,
            ignored_terms=ignored_terms,
        )
        context.retrieval_queries = build_contextual_queries(context)
        return context


def analyze_product_context(
    product_name: str | None = None,
    ingredients: Sequence[str] | None = None,
    purpose: str | None = None,
    product_type: str | None = None,
    jurisdiction: str | None = None,
    traditional_knowledge: bool | None = None,
) -> ProductContext:
    """Convenience API required by the integration contract."""
    return ProductContextEngine().analyze(
        product_name=product_name,
        ingredients=ingredients,
        purpose=purpose,
        product_type=product_type,
        jurisdiction=jurisdiction,
        traditional_knowledge=traditional_knowledge,
    )


def build_contextual_queries(context: ProductContext) -> list[str]:
    """Build retrieval queries from product context, never from ingredient alone."""
    ingredients = context.normalized_ingredients or context.ingredients
    ingredient_text = " ".join(dict.fromkeys(ingredients))
    scientific_text = " ".join(context.scientific_names[:3])
    parts = []
    if context.normalized_product_name:
        parts.append(context.normalized_product_name)
    if ingredient_text:
        parts.append(ingredient_text)
    if context.intended_use:
        parts.append(context.intended_use)
    if context.product_form:
        parts.append(context.product_form)
    if context.product_category and context.product_category != "UNKNOWN":
        parts.append(context.product_category)
    if context.jurisdiction:
        parts.append(context.jurisdiction)
    if context.traditional_knowledge is True:
        parts.append("traditional knowledge")
    elif context.traditional_knowledge is False:
        parts.append("non-traditional context")
    if scientific_text:
        parts.append(scientific_text)

    base = " ".join(dict.fromkeys(ProductContextEngine._norm(x) for x in parts if x))
    if not base:
        return []

    queries = [base]
    if scientific_text:
        q = " ".join(dict.fromkeys(
            x for x in [
                ingredient_text, scientific_text, context.intended_use,
                context.product_form, context.jurisdiction
            ] if x
        ))
        queries.append(ProductContextEngine._norm(q))
    if context.intended_use:
        q = " ".join(dict.fromkeys(
            x for x in [
                context.normalized_product_name or ingredient_text,
                context.intended_use,
                context.product_category if context.product_category != "UNKNOWN" else None,
                context.jurisdiction,
            ] if x
        ))
        queries.append(ProductContextEngine._norm(q))

    return list(dict.fromkeys(q for q in queries if q))


def clarification_question(context: ProductContext) -> str:
    """Return the prescribed clarification prompt for ambiguous product context."""
    if not context.requires_clarification:
        return ""
    return (
        "What is the intended use of the product? For example: food/spice, "
        "cosmetic/topical, Ayurvedic preparation, supplement, or something else?"
    )


__all__ = [
    "ProductContext",
    "ProductContextEngine",
    "analyze_product_context",
    "build_contextual_queries",
    "clarification_question",
]
