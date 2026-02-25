# backend/agents/conversation/models.py

from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ═════════════════════════════════════════════════════════════════════════════
# REQUIREMENT SPEC — IR-ready structured container
# This is the single source of truth for everything the conversation collects.
# ConversationState.fields is now a RequirementSpec, not ExtractedFields.
# ═════════════════════════════════════════════════════════════════════════════

class RequirementSlotStatus(BaseModel):
    """
    Per-slot extraction quality metadata.
    Drives follow-up question routing before IR compilation.
    """
    status:     Literal["missing", "partial", "complete", "uncertain"] = "missing"
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    evidence:   list[str]       = Field(default_factory=list)


class LayoutZoneSpec(BaseModel):
    """
    Semantic placement unit → LayoutIR.
    One entry per component or region on the page.
    """
    zone_id:    str
    component:  str                       # e.g. "DataTable", "PrimaryButton", "Modal"
    anchor:     Optional[str] = None      # e.g. "bottom-right", "center", "top-left"
    size_hint:  Optional[str] = None      # e.g. "full-width", "40%", "auto"
    z_layer:    Optional[str] = None      # e.g. "base", "overlay"
    notes:      Optional[str] = None


class ComponentSpec(BaseModel):
    """
    Component inventory entry → ComponentTreeIR.
    """
    component_id: str
    kind:         str                        # React component name, e.g. "DataTable"
    label:        Optional[str]  = None
    zone_id:      Optional[str]  = None      # Links to LayoutZoneSpec.zone_id
    children:     list[str]      = Field(default_factory=list)
    props:        dict[str, str] = Field(default_factory=dict)


class EntitySpec(BaseModel):
    """
    Single data entity → DataIR.
    """
    name:           str
    fields:         list[str] = Field(default_factory=list)
    computed:       list[str] = Field(default_factory=list)   # e.g. ["bmi"]
    display_fields: list[str] = Field(default_factory=list)   # subset shown in UI
    filters:        list[str] = Field(default_factory=list)
    sort_by:        Optional[str]  = None
    pagination:     Optional[bool] = None


class ActionSpec(BaseModel):
    """
    User interaction entry → BehaviorIR (triggers).
    """
    action_id:             str
    trigger:               str              # e.g. "button_click", "row_select"
    target_component_id:   Optional[str] = None
    operation:             str              # e.g. "open_modal", "calculate_bmi"
    payload:               dict[str, str] = Field(default_factory=dict)
    validation_rules:      list[str]      = Field(default_factory=list)
    requires_confirmation: bool           = False


class FeedbackSpec(BaseModel):
    """
    Post-action UX behavior → BehaviorIR (outcomes).
    """
    action_id:         str
    loading_indicator: Optional[str] = None   # e.g. "spinner", "skeleton"
    success_message:   Optional[str] = None
    error_message:     Optional[str] = None
    ui_updates:        list[str]     = Field(default_factory=list)
    # e.g. ["close_modal", "refresh_table", "display_result_inline"]


class StyleSpec(BaseModel):
    """
    Visual intent → Theme + Template resolver.
    """
    tone:         Optional[str]                                           = None
    theme:        Optional[Literal["light", "dark", "system"]]           = None
    density:      Optional[Literal["compact", "comfortable", "spacious"]] = None
    color_intent: Optional[str]                                           = None
    notes:        Optional[str]                                           = None


class A11ySpec(BaseModel):
    """
    Accessibility requirements → BehaviorIR + ComponentTreeIR checks.
    """
    keyboard_navigation: Optional[bool] = None
    semantic_landmarks:  Optional[bool] = None
    required_labels:     list[str]      = Field(default_factory=list)
    focus_notes:         Optional[str]  = None
    contrast_notes:      Optional[str]  = None


class ResponsiveSpec(BaseModel):
    """
    Breakpoint + adaptation rules → LayoutIR variants.
    """
    strategy:        Optional[Literal["desktop-first", "mobile-first", "adaptive"]] = None
    breakpoints:     dict[str, int] = Field(default_factory=dict)
    collapse_rules:  list[str]      = Field(default_factory=list)
    hidden_on_small: list[str]      = Field(default_factory=list)


class ProductContextSpec(BaseModel):
    """
    Product/business context captured from conversation.
    Maps to planner defaults before IR compilation.
    """
    product_type:      Optional[str] = None
    domain:            Optional[str] = None
    audience:          Optional[str] = None
    primary_platform:  Optional[Literal["web", "mobile_web", "desktop_web"]] = None
    notes:             Optional[str] = None


class DesignIntentSpec(BaseModel):
    """
    UX intent and priorities.
    Maps to hierarchy, interaction density, and flow strategy in IR.
    """
    core_tasks:            list[str] = Field(default_factory=list)
    visual_tone:           Optional[str] = None
    usability_priorities:  list[str] = Field(default_factory=list)
    trust_signals:         list[str] = Field(default_factory=list)
    notes:                 Optional[str] = None


class DesignSystemSpec(BaseModel):
    """
    Design-system level constraints/preferences.
    Maps to component/token binding decisions in generated React output.
    """
    system_name:        Optional[str] = None
    component_library:  Optional[str] = None
    icon_set:           Optional[str] = None
    token_source:       Optional[str] = None
    tailwind_preset:    Optional[str] = None
    notes:              Optional[str] = None


# ── RequirementSpec ───────────────────────────────────────────────────────────

class RequirementSpec(BaseModel):
    """
    Live structured container for everything gathered from the conversation.

    Replaces ExtractedFields as ConversationState.fields.
    This is the direct input to all 4 sub-IR compilers.

    Slot → Sub-IR mapping:
        page_goal    → Planner context
        layout_zones → LayoutIR
        components   → ComponentTreeIR
        entities     → DataIR
        actions      → BehaviorIR (triggers)
        feedback     → BehaviorIR (outcomes)
        style        → Theme + Template resolver
    """
    page_goal:     Optional[str]        = None
    layout_zones:  list[LayoutZoneSpec] = Field(default_factory=list)
    components:    list[ComponentSpec]  = Field(default_factory=list)
    entities:      list[EntitySpec]     = Field(default_factory=list)
    actions:       list[ActionSpec]     = Field(default_factory=list)
    feedback:      list[FeedbackSpec]   = Field(default_factory=list)
    style:         StyleSpec            = Field(default_factory=StyleSpec)
    accessibility: A11ySpec            = Field(default_factory=A11ySpec)
    responsive:    ResponsiveSpec       = Field(default_factory=ResponsiveSpec)
    product_context: ProductContextSpec = Field(default_factory=ProductContextSpec)
    design_intent:   DesignIntentSpec   = Field(default_factory=DesignIntentSpec)
    design_system:   DesignSystemSpec   = Field(default_factory=DesignSystemSpec)
    constraints:   list[str]            = Field(default_factory=list)

    # Per-slot extraction quality — drives gap router
    slot_status: dict[str, RequirementSlotStatus] = Field(default_factory=dict)

    # Required slots for IR generation — others are optional
    _REQUIRED: list[str] = [
        "page_goal",
        "layout_zones",
        "components",
        "entities",
        "actions",
        "feedback",
        "style",
    ]

    # ── Completeness ──────────────────────────────────────────────────────────

    @property
    def missing_fields(self) -> list[str]:
        missing = []
        for slot in self._REQUIRED:
            value = getattr(self, slot)
            if value is None:
                missing.append(slot)
            elif isinstance(value, str) and not value.strip():
                missing.append(slot)
            elif isinstance(value, list) and len(value) == 0:
                missing.append(slot)
            elif isinstance(value, StyleSpec):
                filled = any(
                    getattr(value, f) is not None
                    for f in ["tone", "theme", "density", "color_intent"]
                )
                if not filled:
                    missing.append(slot)
        return missing

    @property
    def is_complete(self) -> bool:
        return len(self.missing_fields) == 0

    def update_slot_status(
        self, slot: str, status: str, confidence: float = 1.0
    ) -> None:
        self.slot_status[slot] = RequirementSlotStatus(
            status=status, confidence=confidence
        )

    # ── Merge helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _clean_str(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned if cleaned else None

    @staticmethod
    def _clean_str_list(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        out: list[str] = []
        for value in values:
            cleaned = RequirementSpec._clean_str(value)
            if cleaned and cleaned not in out:
                out.append(cleaned)
        return out

    @staticmethod
    def _slug(value: str) -> str:
        return (
            value.strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

    @staticmethod
    def _normalize_constraint(value: Any) -> Optional[str]:
        cleaned = RequirementSpec._clean_str(value)
        if not cleaned:
            return None
        return (
            cleaned.lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

    def _next_component_id(
        self,
        kind: str,
        existing_ids: set[str],
        *,
        start: int = 1,
    ) -> str:
        base = f"cmp_{self._slug(kind or 'component')}"
        index = max(start, 1)
        candidate = f"{base}_{index}"
        while candidate in existing_ids:
            index += 1
            candidate = f"{base}_{index}"
        return candidate

    def merge_entities(self, incoming: list[dict]) -> list[str]:
        """Merge incoming entity dicts into self.entities. Returns updated names."""
        updated: list[str] = []
        index = {e.name.lower(): i for i, e in enumerate(self.entities)}

        for raw in incoming:
            if not isinstance(raw, dict):
                continue

            name = self._clean_str(raw.get("name"))
            if not name:
                continue

            if name.lower() in index:
                existing = self.entities[index[name.lower()]]
                changed = False

                new_fields = [f for f in self._clean_str_list(raw.get("fields")) if f not in existing.fields]
                new_computed = [f for f in self._clean_str_list(raw.get("computed")) if f not in existing.computed]
                new_display = [f for f in self._clean_str_list(raw.get("display_fields")) if f not in existing.display_fields]
                new_filters = [f for f in self._clean_str_list(raw.get("filters")) if f not in existing.filters]

                if new_fields:
                    existing.fields += new_fields
                    changed = True
                if new_computed:
                    existing.computed += new_computed
                    changed = True
                if new_display:
                    existing.display_fields += new_display
                    changed = True
                if new_filters:
                    existing.filters += new_filters
                    changed = True

                sort_by = self._clean_str(raw.get("sort_by"))
                if sort_by and existing.sort_by != sort_by:
                    existing.sort_by = sort_by
                    changed = True

                pagination = raw.get("pagination")
                if isinstance(pagination, bool) and existing.pagination != pagination:
                    existing.pagination = pagination
                    changed = True

                if changed:
                    updated.append(name)
            else:
                payload = {
                    "name": name,
                    "fields": self._clean_str_list(raw.get("fields")),
                    "computed": self._clean_str_list(raw.get("computed")),
                    "display_fields": self._clean_str_list(raw.get("display_fields")),
                    "filters": self._clean_str_list(raw.get("filters")),
                }

                sort_by = self._clean_str(raw.get("sort_by"))
                if sort_by:
                    payload["sort_by"] = sort_by

                pagination = raw.get("pagination")
                if isinstance(pagination, bool):
                    payload["pagination"] = pagination

                try:
                    self.entities.append(EntitySpec(**payload))
                    index[name.lower()] = len(self.entities) - 1
                    updated.append(name)
                except Exception:
                    continue

        return updated

    def merge_layout_zones(self, incoming: list[dict]) -> list[str]:
        """Merge incoming layout zone dicts. Returns updated zone_ids."""
        updated: list[str] = []
        index = {z.zone_id.lower(): i for i, z in enumerate(self.layout_zones)}

        for raw in incoming:
            if not isinstance(raw, dict):
                continue

            component = (
                self._clean_str(raw.get("component"))
                or self._clean_str(raw.get("kind"))
                or self._clean_str(raw.get("type"))
                or "Unknown"
            )

            zone_id = self._clean_str(raw.get("zone_id"))
            if not zone_id and component != "Unknown":
                zone_id = f"zone_{self._slug(component)}"
            if not zone_id:
                continue

            if zone_id.lower() in index:
                z = self.layout_zones[index[zone_id.lower()]]
                changed = False

                new_values = {
                    "component": component,
                    "anchor": self._clean_str(raw.get("anchor")),
                    "size_hint": self._clean_str(raw.get("size_hint")),
                    "z_layer": self._clean_str(raw.get("z_layer")),
                    "notes": self._clean_str(raw.get("notes")),
                }

                for attr, value in new_values.items():
                    if value is not None and getattr(z, attr) != value:
                        setattr(z, attr, value)
                        changed = True

                if changed:
                    updated.append(zone_id)
            else:
                payload = {
                    "zone_id": zone_id,
                    "component": component,
                    "anchor": self._clean_str(raw.get("anchor")),
                    "size_hint": self._clean_str(raw.get("size_hint")),
                    "z_layer": self._clean_str(raw.get("z_layer")),
                    "notes": self._clean_str(raw.get("notes")),
                }

                try:
                    self.layout_zones.append(LayoutZoneSpec(**payload))
                    index[zone_id.lower()] = len(self.layout_zones) - 1
                    updated.append(zone_id)
                except Exception:
                    continue

        return updated

    def merge_components(self, incoming: list[dict]) -> list[str]:
        """Merge incoming component dicts. Returns updated component_ids."""
        updated: list[str] = []
        index = {c.component_id.lower(): i for i, c in enumerate(self.components)}
        zone_index = {
            c.zone_id.lower(): i
            for i, c in enumerate(self.components)
            if c.zone_id
        }
        existing_ids = {c.component_id for c in self.components}

        for raw in incoming:
            if not isinstance(raw, dict):
                continue

            kind = (
                self._clean_str(raw.get("kind"))
                or self._clean_str(raw.get("component"))
                or self._clean_str(raw.get("type"))
                or "UnknownComponent"
            )
            zone_id = self._clean_str(raw.get("zone_id"))
            incoming_id = self._clean_str(raw.get("component_id"))
            matched_idx: Optional[int] = None

            if incoming_id and incoming_id.lower() in index:
                matched_idx = index[incoming_id.lower()]
            elif zone_id and zone_id.lower() in zone_index:
                matched_idx = zone_index[zone_id.lower()]

            if matched_idx is not None:
                component = self.components[matched_idx]
                changed = False
                old_zone = component.zone_id
                old_component_id = component.component_id

                # If an explicit id arrives for an auto-seeded zone component,
                # adopt that id to avoid duplicate entries for the same zone.
                if (
                    incoming_id
                    and incoming_id != component.component_id
                    and incoming_id.lower() not in index
                ):
                    component.component_id = incoming_id
                    existing_ids.discard(old_component_id)
                    existing_ids.add(incoming_id)
                    index.pop(old_component_id.lower(), None)
                    index[incoming_id.lower()] = matched_idx

                    for item in self.components:
                        item.children = [
                            incoming_id if child == old_component_id else child
                            for child in item.children
                        ]
                    for action in self.actions:
                        if action.target_component_id == old_component_id:
                            action.target_component_id = incoming_id
                    changed = True

                if kind and component.kind != kind:
                    component.kind = kind
                    changed = True

                label = self._clean_str(raw.get("label"))
                if label and component.label != label:
                    component.label = label
                    changed = True

                if zone_id and component.zone_id != zone_id:
                    component.zone_id = zone_id
                    changed = True

                if old_zone and old_zone.lower() in zone_index and zone_index[old_zone.lower()] == matched_idx:
                    zone_index.pop(old_zone.lower(), None)
                if component.zone_id:
                    zone_index[component.zone_id.lower()] = matched_idx

                new_children = [
                    child
                    for child in self._clean_str_list(raw.get("children"))
                    if child not in component.children
                ]
                if new_children:
                    component.children += new_children
                    changed = True

                props = raw.get("props")
                if isinstance(props, dict):
                    for prop_key, prop_value in props.items():
                        clean_key = self._clean_str(prop_key)
                        clean_value = self._clean_str(prop_value)
                        if clean_key and clean_value and component.props.get(clean_key) != clean_value:
                            component.props[clean_key] = clean_value
                            changed = True

                if changed and component.component_id not in updated:
                    updated.append(component.component_id)
                continue

            component_id = incoming_id or self._next_component_id(
                kind,
                existing_ids,
                start=len(existing_ids) + 1,
            )

            payload = {
                "component_id": component_id,
                "kind": kind,
                "label": self._clean_str(raw.get("label")),
                "zone_id": zone_id,
                "children": self._clean_str_list(raw.get("children")),
                "props": {},
            }
            props = raw.get("props")
            if isinstance(props, dict):
                payload["props"] = {
                    key: value
                    for key, value in (
                        (self._clean_str(prop_key), self._clean_str(prop_value))
                        for prop_key, prop_value in props.items()
                    )
                    if key and value
                }

            try:
                self.components.append(ComponentSpec(**payload))
                existing_ids.add(component_id)
                index[component_id.lower()] = len(self.components) - 1
                if zone_id:
                    zone_index[zone_id.lower()] = len(self.components) - 1
                updated.append(component_id)
            except Exception:
                continue

        return updated

    def ensure_components_from_layout(self) -> list[str]:
        """
        Ensures each layout zone has at least one mapped component.
        Returns component IDs created from layout defaults.
        """
        created: list[str] = []
        existing_ids = {c.component_id for c in self.components}
        zone_to_component = {
            c.zone_id: c.component_id
            for c in self.components
            if c.zone_id
        }

        for zone in self.layout_zones:
            if zone.zone_id in zone_to_component:
                continue

            component_id = self._next_component_id(
                zone.component,
                existing_ids,
                start=len(existing_ids) + 1,
            )
            self.components.append(
                ComponentSpec(
                    component_id=component_id,
                    kind=zone.component,
                    zone_id=zone.zone_id,
                )
            )
            existing_ids.add(component_id)
            zone_to_component[zone.zone_id] = component_id
            created.append(component_id)

        return created

    def merge_actions(self, incoming: list[dict]) -> list[str]:
        """Merge incoming action dicts. Returns updated action_ids."""
        updated: list[str] = []
        index = {a.action_id.lower(): i for i, a in enumerate(self.actions)}

        for raw in incoming:
            if not isinstance(raw, dict):
                continue

            action_id = self._clean_str(raw.get("action_id"))
            operation = self._clean_str(raw.get("operation"))
            trigger = self._clean_str(raw.get("trigger"))
            if not action_id and operation:
                action_id = self._slug(operation)
            if not action_id:
                continue

            if action_id.lower() in index:
                action = self.actions[index[action_id.lower()]]
                changed = False

                if trigger and action.trigger != trigger:
                    action.trigger = trigger
                    changed = True
                if operation and action.operation != operation:
                    action.operation = operation
                    changed = True

                target = self._clean_str(raw.get("target_component_id"))
                if target and action.target_component_id != target:
                    action.target_component_id = target
                    changed = True

                payload = raw.get("payload")
                if isinstance(payload, dict):
                    for key, value in payload.items():
                        clean_key = self._clean_str(key)
                        clean_value = self._clean_str(value)
                        if clean_key and clean_value and action.payload.get(clean_key) != clean_value:
                            action.payload[clean_key] = clean_value
                            changed = True

                new_rules = [r for r in self._clean_str_list(raw.get("validation_rules")) if r not in action.validation_rules]
                if new_rules:
                    action.validation_rules += new_rules
                    changed = True

                requires_confirmation = raw.get("requires_confirmation")
                if isinstance(requires_confirmation, bool) and action.requires_confirmation != requires_confirmation:
                    action.requires_confirmation = requires_confirmation
                    changed = True

                if changed:
                    updated.append(action_id)
            else:
                if not trigger or not operation:
                    continue

                payload = {
                    "action_id": action_id,
                    "trigger": trigger,
                    "operation": operation,
                    "target_component_id": self._clean_str(raw.get("target_component_id")),
                    "validation_rules": self._clean_str_list(raw.get("validation_rules")),
                }

                payload_dict = raw.get("payload")
                if isinstance(payload_dict, dict):
                    payload["payload"] = {
                        k: v
                        for k, v in (
                            (self._clean_str(key), self._clean_str(value))
                            for key, value in payload_dict.items()
                        )
                        if k and v
                    }

                requires_confirmation = raw.get("requires_confirmation")
                if isinstance(requires_confirmation, bool):
                    payload["requires_confirmation"] = requires_confirmation

                try:
                    self.actions.append(ActionSpec(**payload))
                    index[action_id.lower()] = len(self.actions) - 1
                    updated.append(action_id)
                except Exception:
                    continue

        return updated

    def merge_feedback(self, incoming: list[dict]) -> list[str]:
        """Merge incoming feedback dicts. Returns updated action_ids."""
        updated: list[str] = []
        index = {f.action_id.lower(): i for i, f in enumerate(self.feedback)}

        for raw in incoming:
            if not isinstance(raw, dict):
                continue

            action_id = self._clean_str(raw.get("action_id"))
            if not action_id:
                continue

            if action_id.lower() in index:
                f = self.feedback[index[action_id.lower()]]
                changed = False
                for attr in ["loading_indicator", "success_message", "error_message"]:
                    value = self._clean_str(raw.get(attr))
                    if value and getattr(f, attr) != value:
                        setattr(f, attr, value)
                        changed = True

                new_updates = [u for u in self._clean_str_list(raw.get("ui_updates")) if u not in f.ui_updates]
                if new_updates:
                    f.ui_updates += new_updates
                    changed = True

                if changed:
                    updated.append(action_id)
            else:
                payload = {
                    "action_id": action_id,
                    "loading_indicator": self._clean_str(raw.get("loading_indicator")),
                    "success_message": self._clean_str(raw.get("success_message")),
                    "error_message": self._clean_str(raw.get("error_message")),
                    "ui_updates": self._clean_str_list(raw.get("ui_updates")),
                }
                try:
                    self.feedback.append(FeedbackSpec(**payload))
                    index[action_id.lower()] = len(self.feedback) - 1
                    updated.append(action_id)
                except Exception:
                    continue

        return updated

    def merge_style(self, incoming: dict) -> bool:
        """Merge style dict into self.style. Returns True if anything changed."""
        if not isinstance(incoming, dict):
            return False

        changed = False
        for attr in ["tone", "theme", "density", "color_intent", "notes"]:
            val = self._clean_str(incoming.get(attr))
            if val and getattr(self.style, attr) != val:
                setattr(self.style, attr, val)
                changed = True
        return changed

    def merge_product_context(self, incoming: dict) -> bool:
        """Merge product context metadata into self.product_context."""
        if not isinstance(incoming, dict):
            return False

        changed = False
        for attr in ["product_type", "domain", "audience", "notes"]:
            val = self._clean_str(incoming.get(attr))
            if val and getattr(self.product_context, attr) != val:
                setattr(self.product_context, attr, val)
                changed = True

        platform = self._clean_str(incoming.get("primary_platform"))
        if platform:
            normalized = platform.lower().replace("-", "_").replace(" ", "_")
            if normalized == "web" and self.product_context.primary_platform != "web":
                self.product_context.primary_platform = "web"
                changed = True
            elif normalized == "mobile_web" and self.product_context.primary_platform != "mobile_web":
                self.product_context.primary_platform = "mobile_web"
                changed = True
            elif normalized == "desktop_web" and self.product_context.primary_platform != "desktop_web":
                self.product_context.primary_platform = "desktop_web"
                changed = True

        return changed

    def merge_design_intent(self, incoming: dict) -> bool:
        """Merge design intent metadata into self.design_intent."""
        if not isinstance(incoming, dict):
            return False

        changed = False
        for attr in ["visual_tone", "notes"]:
            val = self._clean_str(incoming.get(attr))
            if val and getattr(self.design_intent, attr) != val:
                setattr(self.design_intent, attr, val)
                changed = True

        for attr in ["core_tasks", "usability_priorities", "trust_signals"]:
            existing = getattr(self.design_intent, attr)
            new_values = [
                item
                for item in self._clean_str_list(incoming.get(attr))
                if item not in existing
            ]
            if new_values:
                existing.extend(new_values)
                changed = True

        return changed

    def merge_design_system(self, incoming: dict) -> bool:
        """Merge design system/tooling metadata into self.design_system."""
        if not isinstance(incoming, dict):
            return False

        changed = False
        for attr in [
            "system_name",
            "component_library",
            "icon_set",
            "token_source",
            "tailwind_preset",
            "notes",
        ]:
            val = self._clean_str(incoming.get(attr))
            if val and getattr(self.design_system, attr) != val:
                setattr(self.design_system, attr, val)
                changed = True

        return changed

    def merge_accessibility(self, incoming: dict) -> bool:
        """Merge accessibility dict into self.accessibility."""
        if not isinstance(incoming, dict):
            return False

        changed = False

        for attr in ["keyboard_navigation", "semantic_landmarks"]:
            value = incoming.get(attr)
            if isinstance(value, bool) and getattr(self.accessibility, attr) != value:
                setattr(self.accessibility, attr, value)
                changed = True

        new_labels = [
            label
            for label in self._clean_str_list(incoming.get("required_labels"))
            if label not in self.accessibility.required_labels
        ]
        if new_labels:
            self.accessibility.required_labels += new_labels
            changed = True

        for attr in ["focus_notes", "contrast_notes"]:
            value = self._clean_str(incoming.get(attr))
            if value and getattr(self.accessibility, attr) != value:
                setattr(self.accessibility, attr, value)
                changed = True

        return changed

    def merge_constraints(self, incoming: list[Any]) -> list[str]:
        """Merge canonical guideline constraints into self.constraints."""
        if not isinstance(incoming, list):
            return []

        updated: list[str] = []
        for item in incoming:
            normalized = self._normalize_constraint(item)
            if not normalized:
                continue
            if normalized not in self.constraints:
                self.constraints.append(normalized)
                updated.append(normalized)
        return updated

    # ── Human-readable summary for confirm_node ───────────────────────────────

    def summary(self) -> str:
        lines = []

        lines.append(f"**Goal:** {self.page_goal or '—'}")

        if self.layout_zones:
            lines.append("\n**Layout:**")
            for z in self.layout_zones:
                pos = z.anchor or "unpositioned"
                size = f" ({z.size_hint})" if z.size_hint else ""
                lines.append(f"  • {z.component} → {pos}{size}")
        else:
            lines.append("\n**Layout:** —")

        if self.components:
            lines.append("\n**Components:**")
            for c in self.components:
                zone = f" @ {c.zone_id}" if c.zone_id else ""
                lines.append(f"  • [{c.component_id}] {c.kind}{zone}")
        else:
            lines.append("\n**Components:** —")

        if self.entities:
            lines.append("\n**Entities:**")
            for e in self.entities:
                fields_str   = ", ".join(e.fields) if e.fields else "no fields yet"
                computed_str = f" | computed: {', '.join(e.computed)}" if e.computed else ""
                lines.append(f"  • {e.name}: [{fields_str}]{computed_str}")
        else:
            lines.append("\n**Entities:** —")

        if self.actions:
            lines.append("\n**Actions:**")
            for a in self.actions:
                lines.append(f"  • [{a.action_id}] {a.trigger} → {a.operation}")
        else:
            lines.append("\n**Actions:** —")

        if self.feedback:
            lines.append("\n**Feedback:**")
            for f in self.feedback:
                updates = ", ".join(f.ui_updates) if f.ui_updates else "—"
                msg     = f" | success: {f.success_message}" if f.success_message else ""
                lines.append(f"  • [{f.action_id}] → {updates}{msg}")
        else:
            lines.append("\n**Feedback:** —")

        s = self.style
        style_parts = [
            f"theme={s.theme}"           if s.theme        else None,
            f"density={s.density}"       if s.density      else None,
            f"tone={s.tone}"             if s.tone         else None,
            f"color={s.color_intent}"    if s.color_intent else None,
        ]
        style_str = ", ".join(p for p in style_parts if p) or "—"
        lines.append(f"\n**Style:** {style_str}")

        a = self.accessibility
        a11y_parts = [
            f"keyboard_navigation={a.keyboard_navigation}" if a.keyboard_navigation is not None else None,
            f"semantic_landmarks={a.semantic_landmarks}" if a.semantic_landmarks is not None else None,
            f"required_labels={', '.join(a.required_labels)}" if a.required_labels else None,
        ]
        a11y_str = ", ".join(p for p in a11y_parts if p) or "—"
        lines.append(f"\n**Accessibility:** {a11y_str}")

        constraints_str = ", ".join(self.constraints) if self.constraints else "—"
        lines.append(f"\n**Guideline Constraints:** {constraints_str}")

        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# CONVERSATION PRIMITIVES
# ═════════════════════════════════════════════════════════════════════════════

class Message(BaseModel):
    role:    Literal["user", "assistant", "system"]
    content: str


class ConversationState(BaseModel):
    """
    Full state passed between every graph node.
    fields is now a RequirementSpec — structured, typed, IR-ready.
    active_agent logged on every node transition for tracing.
    """
    messages:     list[Message]   = Field(default_factory=list)
    fields:       RequirementSpec = Field(default_factory=RequirementSpec)
    mode:         Literal[
                    "free_chat",
                    "fill_gaps",
                    "confirm",
                    "done"
                  ]               = "free_chat"
    current_gap:  Optional[str]   = None
    confirmed:    bool            = False
    active_agent: Optional[str]   = None
    guideline_violations: list[str] = Field(default_factory=list)
    recommendation_snapshot: dict[str, Any] = Field(default_factory=dict)
    gap_ask_counts: dict[str, int] = Field(default_factory=dict)

    @property
    def missing(self) -> list[str]:
        return self.fields.missing_fields

    def add_message(self, role: Literal["user", "assistant"], content: str) -> None:
        self.messages.append(Message(role=role, content=content))

    def to_lc_messages(self) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def free_chat_turns(self) -> int:
        return sum(1 for m in self.messages if m.role == "user")


# ═════════════════════════════════════════════════════════════════════════════
# UIPLAN — final typed handoff to IR compiler
# ═════════════════════════════════════════════════════════════════════════════

class UIPlan(BaseModel):
    """
    Confirmed output of done_node → direct input to ir_compiler.compile().
    Fully typed — no string flattening.
    """
    page_goal:     str
    layout_zones:  list[LayoutZoneSpec]
    components:    list[ComponentSpec]
    entities:      list[EntitySpec]
    actions:       list[ActionSpec]
    feedback:      list[FeedbackSpec]
    style:         StyleSpec
    accessibility: A11ySpec
    responsive:    ResponsiveSpec
    constraints:   list[str]

    @classmethod
    def from_spec(cls, spec: RequirementSpec) -> "UIPlan":
        """Build UIPlan from a confirmed RequirementSpec."""
        return cls(
            page_goal     = spec.page_goal or "",
            layout_zones  = spec.layout_zones,
            components    = spec.components,
            entities      = spec.entities,
            actions       = spec.actions,
            feedback      = spec.feedback,
            style         = spec.style,
            accessibility = spec.accessibility,
            responsive    = spec.responsive,
            constraints   = spec.constraints,
        )
