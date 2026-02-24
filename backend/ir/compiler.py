from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from backend.agents.conversation.models import ComponentSpec, UIPlan

from .models import (
    BehaviorIR,
    CompileMetadataIR,
    CompiledIRBundle,
    ComponentNodeIR,
    ComponentTreeIR,
    DataEntityIR,
    DataIR,
    InteractionIR,
    LayoutIR,
    LayoutZoneIR,
    PlacementIR,
)


class IRCompiler:
    def compile(
        self,
        ui_plan: UIPlan,
        *,
        gate_mode: Literal["hybrid", "hard", "advisory"] = "hybrid",
    ) -> CompiledIRBundle:
        warnings: list[str] = []
        autofixes: list[str] = []

        components = self._ensure_components(ui_plan, warnings=warnings, autofixes=autofixes)
        behavior = self._map_behavior(
            ui_plan,
            components=components,
            warnings=warnings,
            autofixes=autofixes,
        )
        component_tree = self._map_component_tree(ui_plan, components=components, warnings=warnings)
        layout = self._map_layout(ui_plan, components=components, warnings=warnings)
        data = self._map_data(ui_plan)

        metadata = CompileMetadataIR(
            ir_version="v1",
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            warnings=warnings,
            autofixes=autofixes,
            gate_mode=gate_mode,
        )

        return CompiledIRBundle(
            component_tree=component_tree,
            layout=layout,
            data=data,
            behavior=behavior,
            metadata=metadata,
        )

    def _ensure_components(
        self,
        ui_plan: UIPlan,
        *,
        warnings: list[str],
        autofixes: list[str],
    ) -> list[ComponentSpec]:
        components = [component.model_copy(deep=True) for component in ui_plan.components]
        existing_ids = {component.component_id for component in components}

        if not components and ui_plan.layout_zones:
            for index, zone in enumerate(ui_plan.layout_zones, start=1):
                component_id = self._next_component_id(zone.component, existing_ids, start=index)
                components.append(
                    ComponentSpec(
                        component_id=component_id,
                        kind=zone.component,
                        zone_id=zone.zone_id,
                    )
                )
                existing_ids.add(component_id)
            self._append_unique(autofixes, "Auto-seeded components from layout_zones.")

        zone_to_component = {
            component.zone_id: component.component_id
            for component in components
            if component.zone_id
        }
        for zone in ui_plan.layout_zones:
            if zone.zone_id in zone_to_component:
                continue
            component_id = self._next_component_id(zone.component, existing_ids)
            components.append(
                ComponentSpec(
                    component_id=component_id,
                    kind=zone.component,
                    zone_id=zone.zone_id,
                )
            )
            existing_ids.add(component_id)
            zone_to_component[zone.zone_id] = component_id
            self._append_unique(
                autofixes,
                f"Added component for unmapped layout zone: {zone.zone_id}.",
            )

        unmatched_zone_ids = [zone.zone_id for zone in ui_plan.layout_zones if zone.zone_id not in zone_to_component]
        if unmatched_zone_ids:
            self._append_unique(
                warnings,
                f"Unmatched layout zones after component normalization: {', '.join(unmatched_zone_ids)}.",
            )

        return components

    def _map_component_tree(
        self,
        ui_plan: UIPlan,
        *,
        components: list[ComponentSpec],
        warnings: list[str],
    ) -> ComponentTreeIR:
        known_ids = {component.component_id for component in components}
        child_ids: set[str] = set()
        nodes: list[ComponentNodeIR] = []

        for component in components:
            valid_children = [child for child in component.children if child in known_ids]
            dropped = [child for child in component.children if child not in known_ids]
            if dropped:
                self._append_unique(
                    warnings,
                    f"Component {component.component_id} references unknown children: {', '.join(dropped)}.",
                )
            child_ids.update(valid_children)

            a11y_labels = ui_plan.accessibility.required_labels if "icon" in component.kind.lower() else []
            nodes.append(
                ComponentNodeIR(
                    component_id=component.component_id,
                    kind=component.kind,
                    zone_id=component.zone_id,
                    children=valid_children,
                    props=component.props,
                    a11y_labels=a11y_labels,
                )
            )

        root_children = [component.component_id for component in components if component.component_id not in child_ids]
        nodes.insert(
            0,
            ComponentNodeIR(
                component_id="root",
                kind="PageRoot",
                children=root_children,
            ),
        )

        return ComponentTreeIR(root_id="root", nodes=nodes)

    def _map_layout(
        self,
        ui_plan: UIPlan,
        *,
        components: list[ComponentSpec],
        warnings: list[str],
    ) -> LayoutIR:
        component_by_zone = {
            component.zone_id: component.component_id
            for component in components
            if component.zone_id
        }

        zones: list[LayoutZoneIR] = []
        for zone in ui_plan.layout_zones:
            component_id = component_by_zone.get(zone.zone_id)
            if component_id is None:
                component_id = self._next_component_id(zone.component, set(component_by_zone.values()))
                self._append_unique(
                    warnings,
                    f"No component found for layout zone {zone.zone_id}; using synthetic component id {component_id}.",
                )

            placement = self._resolve_placement(
                zone.anchor,
                size_hint=zone.size_hint,
                z_layer=zone.z_layer,
                zone_id=zone.zone_id,
                warnings=warnings,
            )
            zones.append(
                LayoutZoneIR(
                    zone_id=zone.zone_id,
                    component_id=component_id,
                    anchor=zone.anchor,
                    size_hint=zone.size_hint,
                    z_layer=zone.z_layer,
                    placement=placement,
                )
            )

        strategy = ui_plan.responsive.strategy or "desktop-first"
        return LayoutIR(
            strategy=strategy,
            breakpoints=ui_plan.responsive.breakpoints,
            zones=zones,
        )

    def _map_data(self, ui_plan: UIPlan) -> DataIR:
        entities = [
            DataEntityIR(
                name=entity.name,
                fields=entity.fields,
                computed=entity.computed,
                display_fields=entity.display_fields,
                filters=entity.filters,
                sort_by=entity.sort_by,
                pagination=entity.pagination,
            )
            for entity in ui_plan.entities
        ]
        return DataIR(entities=entities)

    def _map_behavior(
        self,
        ui_plan: UIPlan,
        *,
        components: list[ComponentSpec],
        warnings: list[str],
        autofixes: list[str],
    ) -> BehaviorIR:
        component_ids = {component.component_id for component in components}
        feedback_by_action = {feedback.action_id: feedback for feedback in ui_plan.feedback}
        action_ids = {action.action_id for action in ui_plan.actions}

        interactions: list[InteractionIR] = []
        for action in ui_plan.actions:
            target = action.target_component_id
            if target and target not in component_ids:
                components.append(
                    ComponentSpec(
                        component_id=target,
                        kind="UnknownComponent",
                    )
                )
                component_ids.add(target)
                self._append_unique(
                    autofixes,
                    f"Created placeholder component for action target: {target}.",
                )

            feedback = feedback_by_action.get(action.action_id)
            if feedback is None:
                self._append_unique(
                    warnings,
                    f"Action {action.action_id} has no feedback entry.",
                )

            interactions.append(
                InteractionIR(
                    action_id=action.action_id,
                    trigger=action.trigger,
                    operation=action.operation,
                    target_component_id=action.target_component_id,
                    requires_confirmation=action.requires_confirmation,
                    payload=action.payload,
                    validation_rules=action.validation_rules,
                    loading_indicator=feedback.loading_indicator if feedback else None,
                    success_message=feedback.success_message if feedback else None,
                    error_message=feedback.error_message if feedback else None,
                    ui_updates=feedback.ui_updates if feedback else [],
                )
            )

        for feedback in ui_plan.feedback:
            if feedback.action_id not in action_ids:
                self._append_unique(
                    warnings,
                    f"Feedback {feedback.action_id} has no matching action.",
                )

        return BehaviorIR(
            interactions=interactions,
            constraints=ui_plan.constraints,
        )

    def _resolve_placement(
        self,
        anchor: str | None,
        *,
        size_hint: str | None,
        z_layer: str | None,
        zone_id: str,
        warnings: list[str],
    ) -> PlacementIR:
        anchor_key = self._canonical(anchor or "")
        anchor_map = {
            "top_left": ("start", "start"),
            "top_right": ("end", "start"),
            "bottom_left": ("start", "end"),
            "bottom_right": ("end", "end"),
            "center": ("center", "center"),
            "full_width": ("stretch", "start"),
        }

        strategy: Literal["anchor", "overlay", "auto_flow"] = "auto_flow"
        justify: Literal["start", "center", "end", "stretch"] = "start"
        align: Literal["start", "center", "end", "stretch"] = "start"
        width = size_hint
        z_index_token = None

        if self._canonical(z_layer or "") == "overlay":
            strategy = "overlay"
            z_index_token = "overlay"
            if anchor_key in anchor_map:
                justify, align = anchor_map[anchor_key]
            else:
                justify, align = "center", "center"
        elif anchor_key in anchor_map:
            strategy = "anchor"
            justify, align = anchor_map[anchor_key]
        elif anchor_key:
            self._append_unique(
                warnings,
                f"Unknown anchor '{anchor}' on zone {zone_id}; using auto_flow placement.",
            )

        if anchor_key == "full_width" and not width:
            width = "full"

        return PlacementIR(
            strategy=strategy,
            justify=justify,
            align=align,
            width=width,
            z_index_token=z_index_token,
        )

    @staticmethod
    def _append_unique(target: list[str], value: str) -> None:
        if value not in target:
            target.append(value)

    @staticmethod
    def _canonical(value: str) -> str:
        return value.strip().lower().replace("-", "_").replace(" ", "_")

    def _next_component_id(
        self,
        kind: str,
        existing_ids: set[str],
        *,
        start: int = 1,
    ) -> str:
        base = f"cmp_{self._canonical(kind) or 'component'}"
        index = max(start, 1)
        candidate = f"{base}_{index}"
        while candidate in existing_ids:
            index += 1
            candidate = f"{base}_{index}"
        return candidate
