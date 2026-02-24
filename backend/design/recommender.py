from __future__ import annotations

from functools import lru_cache
import re
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from backend.agents.conversation.models import RequirementSpec
from backend.knowledge.loader import (
    CuratedKnowledgePack,
    DesignKnowledgeItem,
    KnowledgeLoaderError,
    RuleKnowledgeItem,
    load_curated_knowledge,
)


DEFAULT_THEME: Literal["light", "dark", "system"] = "light"
DEFAULT_DENSITY: Literal["compact", "comfortable", "spacious"] = "comfortable"
DEFAULT_COLOR_INTENT = "neutral"
DEFAULT_PLATFORM: Literal["web", "mobile_web", "desktop_web"] = "desktop_web"
DEFAULT_COMPONENT_LIBRARY = "shadcn/ui"
DEFAULT_ICON_SET = "lucide"
DEFAULT_TOKEN_SOURCE = "tailwind_tokens"

_CONSTRAINT_PRIORITY = [
    "prefers_reduced_motion",
    "url_state_sync",
    "intl_formatting",
    "forms_labeled",
]
_CONSTRAINT_CHECK_RE = re.compile(r"constraints\s+includes\s+([-a-z0-9_ ]+)", re.IGNORECASE)


class StyleRecommendation(BaseModel):
    theme: Literal["light", "dark", "system"] = DEFAULT_THEME
    density: Literal["compact", "comfortable", "spacious"] = DEFAULT_DENSITY
    color_intent: str = DEFAULT_COLOR_INTENT


class DesignSystemRecommendation(BaseModel):
    component_library: str = DEFAULT_COMPONENT_LIBRARY
    icon_set: str = DEFAULT_ICON_SET
    token_source: str = DEFAULT_TOKEN_SOURCE


class DesignRecommendationSnapshot(BaseModel):
    """
    Deterministic recommendation payload using curated local knowledge packs.
    """

    engine: Literal["deterministic_stub"] = "deterministic_stub"
    primary_platform: Literal["web", "mobile_web", "desktop_web"] = DEFAULT_PLATFORM
    style: StyleRecommendation = Field(default_factory=StyleRecommendation)
    design_system: DesignSystemRecommendation = Field(default_factory=DesignSystemRecommendation)
    constraints: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


@lru_cache(maxsize=1)
def _load_pack() -> CuratedKnowledgePack | None:
    try:
        return load_curated_knowledge()
    except KnowledgeLoaderError:
        return None


def recommend_design_defaults(spec: RequirementSpec) -> DesignRecommendationSnapshot:
    """
    Returns controlled defaults based on current requirement signals.
    Uses curated knowledge pack when available, with deterministic fallback values.
    """
    pack = _load_pack()
    products = pack.products if pack else []
    matched_product = _find_product_profile(spec, products)
    design_system_product = matched_product or _default_product_profile(products)

    platform = spec.product_context.primary_platform or DEFAULT_PLATFORM

    style_defaults = _style_defaults(pack, matched_product)
    style = StyleRecommendation(
        theme=spec.style.theme or style_defaults["theme"],
        density=spec.style.density or style_defaults["density"],
        color_intent=spec.style.color_intent or style_defaults["color_intent"],
    )

    design_defaults = _design_system_defaults(design_system_product)
    design_system = DesignSystemRecommendation(
        component_library=spec.design_system.component_library or design_defaults["component_library"],
        icon_set=spec.design_system.icon_set or design_defaults["icon_set"],
        token_source=spec.design_system.token_source or design_defaults["token_source"],
    )

    constraints = _merge_constraints(
        spec.constraints,
        _default_constraints_for_spec(spec, pack, matched_product),
    )

    notes: list[str] = []
    if pack is not None:
        notes.append("Curated knowledge defaults applied from backend/knowledge.")
    else:
        notes.append("Curated knowledge unavailable; deterministic fallback defaults applied.")

    if matched_product is not None:
        notes.append(f"Matched product profile: {matched_product.id}.")
    elif design_system_product is not None:
        notes.append(f"Applied default product profile for design system: {design_system_product.id}.")

    if _has_form_actions(spec):
        notes.append("Detected form-like actions; forms_labeled default applied.")

    return DesignRecommendationSnapshot(
        primary_platform=platform,
        style=style,
        design_system=design_system,
        constraints=constraints,
        notes=notes,
    )


def _style_defaults(
    pack: CuratedKnowledgePack | None,
    product: DesignKnowledgeItem | None,
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "theme": DEFAULT_THEME,
        "density": DEFAULT_DENSITY,
        "color_intent": DEFAULT_COLOR_INTENT,
    }

    if pack is None or not pack.styles:
        return defaults

    style_item: DesignKnowledgeItem | None = None

    if product is not None:
        style_id = _metadata_str(product, "recommended_style")
        if style_id:
            style_item = _design_item_by_id(pack.styles, style_id)

    if style_item is None:
        style_item = _design_item_by_id(pack.styles, "style_clinical_minimal")

    if style_item is None:
        style_item = pack.styles[0]

    theme = _as_theme(_metadata_str(style_item, "theme"))
    density = _as_density(_metadata_str(style_item, "density"))
    color_intent = _metadata_str(style_item, "color_intent")

    if theme is not None:
        defaults["theme"] = theme
    if density is not None:
        defaults["density"] = density
    if color_intent:
        defaults["color_intent"] = color_intent

    return defaults


def _design_system_defaults(product: DesignKnowledgeItem | None) -> dict[str, str]:
    defaults = {
        "component_library": DEFAULT_COMPONENT_LIBRARY,
        "icon_set": DEFAULT_ICON_SET,
        "token_source": DEFAULT_TOKEN_SOURCE,
    }

    if product is None:
        return defaults

    component_library = _metadata_str(product, "default_component_library")
    icon_set = _metadata_str(product, "default_icon_set")
    token_source = _metadata_str(product, "default_token_source")

    if component_library:
        defaults["component_library"] = component_library
    if icon_set:
        defaults["icon_set"] = icon_set
    if token_source:
        defaults["token_source"] = token_source

    return defaults


def _default_constraints_for_spec(
    spec: RequirementSpec,
    pack: CuratedKnowledgePack | None,
    product: DesignKnowledgeItem | None,
) -> list[str]:
    product_defaults = _metadata_str_list(product, "default_constraints") if product is not None else []
    rule_defaults = _constraint_tokens_from_rules(pack.web_critical_rules) if pack is not None else []

    combined = _merge_constraints(product_defaults, rule_defaults)
    if not combined:
        combined = ["prefers_reduced_motion", "url_state_sync", "intl_formatting", "forms_labeled"]

    include_forms = _has_form_actions(spec)
    return _prioritize_constraints(combined, include_forms=include_forms)


def _constraint_tokens_from_rules(rules: list[RuleKnowledgeItem]) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()

    for rule in rules:
        for check in rule.checks:
            match = _CONSTRAINT_CHECK_RE.search(check)
            if not match:
                continue
            token = _normalize_constraint(match.group(1).split(" when ", 1)[0])
            if token and token not in seen:
                seen.add(token)
                tokens.append(token)

    return tokens


def _prioritize_constraints(tokens: list[str], *, include_forms: bool) -> list[str]:
    normalized = [_normalize_constraint(item) for item in tokens]
    normalized = [item for item in normalized if item]

    out: list[str] = []
    seen: set[str] = set()

    for token in _CONSTRAINT_PRIORITY:
        if token not in normalized:
            continue
        if token == "forms_labeled" and not include_forms:
            continue
        out.append(token)
        seen.add(token)

    for token in normalized:
        if token in seen:
            continue
        if token == "forms_labeled" and not include_forms:
            continue
        out.append(token)
        seen.add(token)

    return out


def _find_product_profile(
    spec: RequirementSpec,
    products: list[DesignKnowledgeItem],
) -> DesignKnowledgeItem | None:
    if not products:
        return None

    product_type = _canonical(spec.product_context.product_type or "")
    domain = _canonical(spec.product_context.domain or "")
    audience = _canonical(spec.product_context.audience or "")

    best_item: DesignKnowledgeItem | None = None
    best_score = 0

    for item in products:
        keys = {
            _canonical(item.id),
            _canonical(item.title),
            *[_canonical(tag) for tag in item.tags],
        }

        score = 0
        if product_type:
            if product_type in keys:
                score += 6
            elif any(product_type in key or key in product_type for key in keys):
                score += 3

        if domain:
            if domain in keys:
                score += 4
            elif any(domain in key for key in keys):
                score += 2

        if audience:
            if audience in keys:
                score += 2
            elif any(audience in key for key in keys):
                score += 1

        if score > best_score:
            best_score = score
            best_item = item

    return best_item if best_score > 0 else None


def _default_product_profile(products: list[DesignKnowledgeItem]) -> DesignKnowledgeItem | None:
    if not products:
        return None

    for item in products:
        marker = item.metadata.get("is_default_profile")
        if marker is True:
            return item

    preferred = _design_item_by_id(products, "product_internal_ops_dashboard")
    if preferred is not None:
        return preferred

    return products[0]


def _design_item_by_id(items: list[DesignKnowledgeItem], item_id: str) -> DesignKnowledgeItem | None:
    target = _canonical(item_id)
    for item in items:
        if _canonical(item.id) == target:
            return item
    return None


def _metadata_str(item: DesignKnowledgeItem, key: str) -> str | None:
    value = item.metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _metadata_str_list(item: DesignKnowledgeItem, key: str) -> list[str]:
    value = item.metadata.get(key)
    if not isinstance(value, list):
        return []

    out: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        cleaned = entry.strip()
        if not cleaned:
            continue
        out.append(cleaned)
    return out


def _as_theme(value: str | None) -> Literal["light", "dark", "system"] | None:
    if value is None:
        return None
    normalized = _canonical(value)
    if normalized in {"light", "dark", "system"}:
        return cast(Literal["light", "dark", "system"], normalized)
    return None


def _as_density(value: str | None) -> Literal["compact", "comfortable", "spacious"] | None:
    if value is None:
        return None
    normalized = _canonical(value)
    if normalized in {"compact", "comfortable", "spacious"}:
        return cast(Literal["compact", "comfortable", "spacious"], normalized)
    return None


def _has_form_actions(spec: RequirementSpec) -> bool:
    for action in spec.actions:
        trigger = action.trigger.lower()
        operation = action.operation.lower()
        if "form" in trigger:
            return True
        if any(token in operation for token in ("create", "update", "save", "submit")):
            return True
    return False


def _merge_constraints(current: list[str], defaults: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    for raw in [*current, *defaults]:
        normalized = _normalize_constraint(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)

    return merged


def _normalize_constraint(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _canonical(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")
