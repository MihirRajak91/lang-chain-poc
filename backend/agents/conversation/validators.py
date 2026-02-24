from __future__ import annotations

from dataclasses import dataclass

from .models import RequirementSpec


@dataclass(frozen=True)
class GuidelineIssue:
    slot: str
    message: str


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


def evaluate_guideline_critical(spec: RequirementSpec) -> list[GuidelineIssue]:
    """
    Minimal critical gate inspired by web-interface-guidelines.
    Returns follow-up questions that must be resolved before confirmation.
    """
    issues: list[GuidelineIssue] = []

    if not spec.accessibility.required_labels:
        issues.append(
            GuidelineIssue(
                slot="accessibility",
                message="List aria-label text for icon-only controls (for example: close button, menu button).",
            )
        )

    if spec.accessibility.keyboard_navigation is not True:
        issues.append(
            GuidelineIssue(
                slot="accessibility",
                message="Should all interactive controls support keyboard navigation (Tab, Enter, Space, Escape)?",
            )
        )

    destructive_without_confirmation = [
        action.action_id
        for action in spec.actions
        if any(
            token in action.operation.lower()
            for token in ("delete", "remove", "destroy", "archive")
        )
        and not action.requires_confirmation
    ]
    if destructive_without_confirmation:
        ids = ", ".join(destructive_without_confirmation)
        issues.append(
            GuidelineIssue(
                slot="actions",
                message=f"Should destructive actions require confirmation or undo? Affected actions: {ids}.",
            )
        )

    if _has_form_actions(spec) and not _has_constraint(spec, "forms_labeled"):
        issues.append(
            GuidelineIssue(
                slot="constraints",
                message="Confirm form requirements: labeled fields, correct input type/inputmode, and autocomplete intent.",
            )
        )

    if _needs_url_state_sync(spec) and not _has_constraint(spec, "url_state_sync"):
        issues.append(
            GuidelineIssue(
                slot="constraints",
                message="Should filters, tabs, and pagination be synchronized to URL query params for deep links?",
            )
        )

    if not _has_constraint(spec, "prefers_reduced_motion", "reduced_motion"):
        issues.append(
            GuidelineIssue(
                slot="constraints",
                message="Should motion honor prefers-reduced-motion (reduced or disabled animation)?",
            )
        )

    if _needs_intl_formatting(spec) and not _has_constraint(spec, "intl_formatting"):
        issues.append(
            GuidelineIssue(
                slot="constraints",
                message="Confirm locale formatting: use Intl.DateTimeFormat / Intl.NumberFormat for user-facing dates and numbers.",
            )
        )

    return issues
