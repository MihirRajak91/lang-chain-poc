from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ComponentNodeIR(BaseModel):
    component_id: str
    kind: str
    zone_id: Optional[str] = None
    parent_id: Optional[str] = None
    children: list[str] = Field(default_factory=list)
    props: dict[str, str] = Field(default_factory=dict)
    a11y_labels: list[str] = Field(default_factory=list)


class ComponentTreeIR(BaseModel):
    root_id: str = "root"
    nodes: list[ComponentNodeIR] = Field(default_factory=list)


class PlacementIR(BaseModel):
    strategy: Literal["anchor", "overlay", "auto_flow"] = "auto_flow"
    justify: Literal["start", "center", "end", "stretch"] = "start"
    align: Literal["start", "center", "end", "stretch"] = "start"
    width: Optional[str] = None
    z_index_token: Optional[str] = None


class LayoutZoneIR(BaseModel):
    zone_id: str
    component_id: str
    anchor: Optional[str] = None
    size_hint: Optional[str] = None
    z_layer: Optional[str] = None
    placement: PlacementIR = Field(default_factory=PlacementIR)


class LayoutIR(BaseModel):
    strategy: Literal["desktop-first", "mobile-first", "adaptive"] = "desktop-first"
    breakpoints: dict[str, int] = Field(default_factory=dict)
    zones: list[LayoutZoneIR] = Field(default_factory=list)


class DataEntityIR(BaseModel):
    name: str
    fields: list[str] = Field(default_factory=list)
    computed: list[str] = Field(default_factory=list)
    display_fields: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    sort_by: Optional[str] = None
    pagination: Optional[bool] = None


class DataIR(BaseModel):
    entities: list[DataEntityIR] = Field(default_factory=list)


class InteractionIR(BaseModel):
    action_id: str
    trigger: str
    operation: str
    target_component_id: Optional[str] = None
    requires_confirmation: bool = False
    payload: dict[str, str] = Field(default_factory=dict)
    validation_rules: list[str] = Field(default_factory=list)
    loading_indicator: Optional[str] = None
    success_message: Optional[str] = None
    error_message: Optional[str] = None
    ui_updates: list[str] = Field(default_factory=list)


class BehaviorIR(BaseModel):
    interactions: list[InteractionIR] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class CompileMetadataIR(BaseModel):
    ir_version: str = "v1"
    generated_at: str
    warnings: list[str] = Field(default_factory=list)
    autofixes: list[str] = Field(default_factory=list)
    gate_mode: Literal["hybrid", "hard", "advisory"] = "hybrid"


class CompiledIRBundle(BaseModel):
    component_tree: ComponentTreeIR
    layout: LayoutIR
    data: DataIR
    behavior: BehaviorIR
    metadata: CompileMetadataIR
