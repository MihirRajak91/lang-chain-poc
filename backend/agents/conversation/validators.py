from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Literal

from backend.knowledge.loader import KnowledgeLoaderError, RuleKnowledgeItem, load_curated_knowledge

from .models import RequirementSpec


@dataclass(frozen=True)
class GuidelineIssue:
    slot: str
    message: str
    severity: Literal["critical", "warning"] = "critical"


@dataclass(frozen=True)
class QualityGateEvaluation:
    gate_mode: Literal["hybrid", "hard", "advisory"]
    critical_violations: list[GuidelineIssue]
    warning_findings: list[GuidelineIssue]
    blocking_findings: list[GuidelineIssue]

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocking_findings)


def _canonical(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _has_constraint(spec: RequirementSpec, *keys: str) -> bool:
    current = {_canonical(item) for item in spec.constraints}
    expected = {_canonical(key) for key in keys}
    return not current.isdisjoint(expected)


def _has_form_actions(spec: RequirementSpec) -> bool:
    for action in spec.actions:
        trigger = action.trigger.lower()
        operation = action.operation.lower()
        if "form" in trigger:
            return True
        if any(token in operation for token in ("create", "update", "save", "submit")):
            return True
    return False


def _needs_url_state_sync(spec: RequirementSpec) -> bool:
    return any(
        entity.filters or entity.sort_by or entity.pagination is True
        for entity in spec.entities
    )


def _needs_intl_formatting(spec: RequirementSpec) -> bool:
    tokens = ("date", "time", "price", "amount", "total", "count", "age", "kg", "cm")
    for entity in spec.entities:
        fields = [*entity.fields, *entity.display_fields, *entity.computed]
        for field in fields:
            field_lower = field.lower()
            if any(token in field_lower for token in tokens):
                return True
    return False


def _destructive_without_confirmation(spec: RequirementSpec) -> list[str]:
    affected: list[str] = []
    for action in spec.actions:
        operation = action.operation.lower()
        if any(token in operation for token in ("delete", "remove", "destroy", "archive")):
            if not action.requires_confirmation:
                affected.append(action.action_id)
    return affected


def _actionable_error_message_present(spec: RequirementSpec) -> bool:
    actionable_tokens = ("retry", "try", "check", "select", "enter", "refresh", "contact", "fix")
    for feedback in spec.feedback:
        message = (feedback.error_message or "").strip().lower()
        if not message:
            continue
        if any(token in message for token in actionable_tokens):
            return True
    return False


def _async_action_missing_loading_feedback(spec: RequirementSpec) -> bool:
    async_tokens = ("load", "fetch", "save", "submit", "calculate", "create", "update", "delete")
    feedback_by_action = {item.action_id: item for item in spec.feedback}

    for action in spec.actions:
        operation = action.operation.lower()
        trigger = action.trigger.lower()
        is_async_like = any(token in operation for token in async_tokens) or "submit" in trigger
        if not is_async_like:
            continue

        feedback = feedback_by_action.get(action.action_id)
        if feedback is None:
            return True
        if feedback.loading_indicator is None:
            return True

    return False


def _fallback_critical_rules() -> list[RuleKnowledgeItem]:
    return [
        RuleKnowledgeItem(
            id="critical_icon_controls_labeled",
            title="Icon-only Controls Need Labels",
            description="List aria-label text for icon-only controls (for example: close button, menu button).",
            severity="critical",
            metadata={"slot": "accessibility"},
        ),
        RuleKnowledgeItem(
            id="critical_keyboard_navigation",
            title="Keyboard Navigation Required",
            description="Should all interactive controls support keyboard navigation (Tab, Enter, Space, Escape)?",
            severity="critical",
            metadata={"slot": "accessibility"},
        ),
        RuleKnowledgeItem(
            id="critical_destructive_action_confirmation",
            title="Destructive Actions Require Confirmation",
            description="Should destructive actions require confirmation or undo?",
            severity="critical",
            metadata={"slot": "actions"},
        ),
        RuleKnowledgeItem(
            id="critical_forms_labeled_and_typed",
            title="Forms Must Be Labeled and Typed",
            description="Confirm form requirements: labeled fields, correct input type/inputmode, and autocomplete intent.",
            severity="critical",
            metadata={"slot": "constraints"},
            checks=["constraints includes forms_labeled"],
        ),
        RuleKnowledgeItem(
            id="critical_url_state_sync_for_filters",
            title="Filter and Pagination State Sync",
            description="Should filters, tabs, and pagination be synchronized to URL query params for deep links?",
            severity="critical",
            metadata={"slot": "constraints"},
            checks=["constraints includes url_state_sync"],
        ),
        RuleKnowledgeItem(
            id="critical_reduced_motion_support",
            title="Respect Prefers Reduced Motion",
            description="Should motion honor prefers-reduced-motion (reduced or disabled animation)?",
            severity="critical",
            metadata={"slot": "constraints"},
            checks=["constraints includes prefers_reduced_motion"],
        ),
        RuleKnowledgeItem(
            id="critical_intl_user_formatting",
            title="Locale-aware User Formatting",
            description="Confirm locale formatting: use Intl.DateTimeFormat / Intl.NumberFormat for user-facing dates and numbers.",
            severity="critical",
            metadata={"slot": "constraints"},
            checks=["constraints includes intl_formatting"],
        ),
    ]


def _fallback_warning_rules() -> list[RuleKnowledgeItem]:
    return [
        RuleKnowledgeItem(
            id="warning_define_core_tasks",
            title="Core Tasks Should Be Captured",
            description="List top core tasks so interaction hierarchy can be optimized for the main workflow.",
            severity="warning",
            metadata={"slot": "design_intent"},
        ),
        RuleKnowledgeItem(
            id="warning_define_component_library",
            title="Component Library Preference",
            description="Specify preferred component library (for example: shadcn/ui, MUI, Mantine) to reduce implementation ambiguity.",
            severity="warning",
            metadata={"slot": "design_system"},
        ),
        RuleKnowledgeItem(
            id="warning_define_responsive_strategy",
            title="Responsive Strategy Should Be Explicit",
            description="Choose responsive strategy: desktop-first, mobile-first, or adaptive.",
            severity="warning",
            metadata={"slot": "responsive"},
        ),
        RuleKnowledgeItem(
            id="warning_semantic_landmarks",
            title="Semantic Landmarks Recommended",
            description="Confirm semantic landmarks for primary regions (header, main, nav, footer).",
            severity="warning",
            metadata={"slot": "accessibility"},
        ),
    ]


@lru_cache(maxsize=1)
def _load_runtime_rules() -> tuple[list[RuleKnowledgeItem], list[RuleKnowledgeItem]]:
    try:
        pack = load_curated_knowledge()
        if pack.web_critical_rules and pack.web_warning_rules:
            return pack.web_critical_rules, pack.web_warning_rules
    except KnowledgeLoaderError:
        pass
    return _fallback_critical_rules(), _fallback_warning_rules()


def _rule_slot(rule: RuleKnowledgeItem, default: str) -> str:
    slot = rule.metadata.get("slot") if isinstance(rule.metadata, dict) else None
    if isinstance(slot, str) and slot.strip():
        return slot.strip()
    return default


def _issue_from_rule(
    rule: RuleKnowledgeItem,
    *,
    default_slot: str,
    default_severity: Literal["critical", "warning"],
    message: str | None = None,
) -> GuidelineIssue:
    severity: Literal["critical", "warning"]
    if rule.severity in ("critical", "warning"):
        severity = rule.severity
    else:
        severity = default_severity

    return GuidelineIssue(
        slot=_rule_slot(rule, default_slot),
        message=(message or rule.description).strip(),
        severity=severity,
    )


_CONSTRAINT_CHECK_RE = re.compile(r"constraints\s+includes\s+([-a-z0-9_ ]+)", re.IGNORECASE)


def _extract_constraint_token(rule: RuleKnowledgeItem) -> str | None:
    for check in rule.checks:
        match = _CONSTRAINT_CHECK_RE.search(check)
        if not match:
            continue
        token = match.group(1).split(" when ", 1)[0].strip()
        normalized = _canonical(token)
        if normalized:
            return normalized
    return None


def _evaluate_critical_rule(rule: RuleKnowledgeItem, spec: RequirementSpec) -> GuidelineIssue | None:
    rule_id = _canonical(rule.id)

    if rule_id == "critical_icon_controls_labeled":
        if not spec.accessibility.required_labels:
            return _issue_from_rule(rule, default_slot="accessibility", default_severity="critical")
        return None

    if rule_id == "critical_keyboard_navigation":
        if spec.accessibility.keyboard_navigation is not True:
            return _issue_from_rule(rule, default_slot="accessibility", default_severity="critical")
        return None

    if rule_id == "critical_destructive_action_confirmation":
        affected = _destructive_without_confirmation(spec)
        if affected:
            ids = ", ".join(affected)
            return _issue_from_rule(
                rule,
                default_slot="actions",
                default_severity="critical",
                message=f"{rule.description} Affected actions: {ids}.",
            )
        return None

    if rule_id == "critical_forms_labeled_and_typed":
        if _has_form_actions(spec) and not _has_constraint(spec, "forms_labeled"):
            return _issue_from_rule(rule, default_slot="constraints", default_severity="critical")
        return None

    if rule_id == "critical_url_state_sync_for_filters":
        if _needs_url_state_sync(spec) and not _has_constraint(spec, "url_state_sync"):
            return _issue_from_rule(rule, default_slot="constraints", default_severity="critical")
        return None

    if rule_id == "critical_reduced_motion_support":
        if not _has_constraint(spec, "prefers_reduced_motion", "reduced_motion"):
            return _issue_from_rule(rule, default_slot="constraints", default_severity="critical")
        return None

    if rule_id == "critical_intl_user_formatting":
        if _needs_intl_formatting(spec) and not _has_constraint(spec, "intl_formatting"):
            return _issue_from_rule(rule, default_slot="constraints", default_severity="critical")
        return None

    token = _extract_constraint_token(rule)
    if token and not _has_constraint(spec, token):
        return _issue_from_rule(rule, default_slot="constraints", default_severity="critical")

    return None


def _evaluate_warning_rule(rule: RuleKnowledgeItem, spec: RequirementSpec) -> GuidelineIssue | None:
    rule_id = _canonical(rule.id)

    if rule_id == "warning_define_core_tasks":
        if not spec.design_intent.core_tasks:
            return _issue_from_rule(rule, default_slot="design_intent", default_severity="warning")
        return None

    if rule_id == "warning_define_component_library":
        if not spec.design_system.component_library:
            return _issue_from_rule(rule, default_slot="design_system", default_severity="warning")
        return None

    if rule_id == "warning_define_responsive_strategy":
        if spec.responsive.strategy is None:
            return _issue_from_rule(rule, default_slot="responsive", default_severity="warning")
        return None

    if rule_id == "warning_semantic_landmarks":
        if spec.accessibility.semantic_landmarks is not True:
            return _issue_from_rule(rule, default_slot="accessibility", default_severity="warning")
        return None

    if rule_id == "warning_loading_feedback_consistency":
        if _async_action_missing_loading_feedback(spec):
            return _issue_from_rule(rule, default_slot="feedback", default_severity="warning")
        return None

    if rule_id == "warning_error_feedback_clarity":
        if not _actionable_error_message_present(spec):
            return _issue_from_rule(rule, default_slot="feedback", default_severity="warning")
        return None

    token = _extract_constraint_token(rule)
    if token and not _has_constraint(spec, token):
        return _issue_from_rule(rule, default_slot="constraints", default_severity="warning")

    return None


def evaluate_guideline_critical(spec: RequirementSpec) -> list[GuidelineIssue]:
    """
    Critical gate checks loaded from curated knowledge rules,
    with deterministic fallback rules if loading fails.
    """
    critical_rules, _ = _load_runtime_rules()

    issues: list[GuidelineIssue] = []
    for rule in critical_rules:
        issue = _evaluate_critical_rule(rule, spec)
        if issue is not None:
            issues.append(issue)

    return issues


def evaluate_guideline_warning(spec: RequirementSpec) -> list[GuidelineIssue]:
    """
    Warning checks loaded from curated knowledge rules,
    with deterministic fallback rules if loading fails.
    """
    _, warning_rules = _load_runtime_rules()

    issues: list[GuidelineIssue] = []
    for rule in warning_rules:
        issue = _evaluate_warning_rule(rule, spec)
        if issue is not None:
            issues.append(issue)

    return issues


def evaluate_quality_gate(
    spec: RequirementSpec,
    gate_mode: Literal["hybrid", "hard", "advisory"] = "hybrid",
) -> QualityGateEvaluation:
    """
    Computes critical/warning findings and determines which are blocking
    under the requested quality-gate policy.
    """
    critical_violations = evaluate_guideline_critical(spec)
    warning_findings = evaluate_guideline_warning(spec)

    if gate_mode == "hard":
        blocking_findings = [*critical_violations, *warning_findings]
    elif gate_mode == "advisory":
        blocking_findings = []
    else:
        blocking_findings = list(critical_violations)

    return QualityGateEvaluation(
        gate_mode=gate_mode,
        critical_violations=critical_violations,
        warning_findings=warning_findings,
        blocking_findings=blocking_findings,
    )
