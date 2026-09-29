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
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence
import json
import re


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ONTOLOGY_PATH = BASE_DIR / "data" / "ingredient_ontology.json"
DEFAULT_EXAMPLES_PATH = BASE_DIR / "data" / "product_context_examples.json"


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
    # RELEVANT / IRRELEVANT / UNDETERMINED: does the product make sense
    # for its ingredients and stated category?
    relevance_status: str = "UNDETERMINED"
    relevance_reasons: list[str] = field(default_factory=list)
    retrieval_queries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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

        self._alias_to_canonical: dict[str, str] = {}
        self._scientific_to_canonical: dict[str, str] = {}
        for canonical, record in self.ontology.items():
            for value in [canonical, *record.get("common_names", []), *record.get("regional_names", [])]:
                self._alias_to_canonical[self._norm(value)] = canonical
            for value in record.get("scientific_names", []):
                self._scientific_to_canonical[self._norm(value)] = canonical

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
        text = re.sub(r"[^a-z0-9\s\-/]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def normalize_ingredient(self, value: str) -> str:
        norm = self._norm(value)
        if norm in self._alias_to_canonical:
            return self._alias_to_canonical[norm]
        if norm in self._scientific_to_canonical:
            return self._scientific_to_canonical[norm]
        return norm

    def _find_ingredients(self, text: str, explicit: Sequence[str] | None) -> list[str]:
        found: list[str] = []
        if explicit:
            found.extend(self.normalize_ingredient(x) for x in explicit if self._norm(x))
        norm_text = self._norm(text)
        # Longest aliases first prevents "tea" from firing before "green tea".
        aliases = sorted(self._alias_to_canonical, key=len, reverse=True)
        for alias in aliases:
            if len(alias) < 3:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", norm_text):
                found.append(self._alias_to_canonical[alias])
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
        if not known:
            return "UNDETERMINED", ["No ingredient found in the ingredient ontology."]

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
            ]
        return "IRRELEVANT", [
            f"'{x}' is not a known {category} ingredient (known uses: "
            f"{', '.join(self.ontology[x].get('common_product_contexts', []))})."
            for x in mismatched
        ]

    def analyze(
        self,
        product_name: str | None = None,
        ingredients: Sequence[str] | None = None,
        purpose: str | None = None,
        product_type: str | None = None,
        jurisdiction: str | None = None,
        traditional_knowledge: bool | None = None,
    ) -> ProductContext:
        combined = " ".join(
            x for x in [product_name or "", purpose or "", product_type or ""]
            if x
        )
        normalized_product = self._norm(product_name or combined)
        ingredient_list = self._find_ingredients(combined, ingredients)
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
        # Nothing recognisable: no known ingredient and no use signal
        # (e.g. random text). Form/type/jurisdiction alone mean nothing.
        stated_use_signal = bool(
            self._match_use(" ".join(x for x in [product_name or "", purpose or ""] if x))
        )
        unrecognized_input = not known_ingredients and not stated_use_signal
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
                "Neither the ingredients nor the intended use are recognised; "
                "please enter real ingredient names and a clear intended use."
            ]
        if relevance_status == "IRRELEVANT":
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
