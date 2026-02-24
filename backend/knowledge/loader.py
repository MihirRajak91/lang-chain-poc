from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class KnowledgeLoaderError(RuntimeError):
    """Base class for curated knowledge loading failures."""


class KnowledgeFileNotFoundError(KnowledgeLoaderError):
    """Raised when an expected curated knowledge file is missing."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"Knowledge file not found: {path}")
        self.path = path


class KnowledgeFormatError(KnowledgeLoaderError):
    """Raised when file JSON is invalid or does not match the expected top-level shape."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"Invalid knowledge format in {path}: {reason}")
        self.path = path
        self.reason = reason


class KnowledgeValidationError(KnowledgeLoaderError):
    """Raised when a list entry fails model validation."""

    def __init__(self, path: Path, index: int, reason: str) -> None:
        super().__init__(f"Knowledge entry validation failed in {path} at index {index}: {reason}")
        self.path = path
        self.index = index
        self.reason = reason


class DesignKnowledgeItem(BaseModel):
    """
    Generic record for curated design knowledge entries.
    Concrete consumers can map these to richer domain models later.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuleKnowledgeItem(BaseModel):
    """
    Generic record for curated rules and checks.
    Severity defaults are intentionally permissive until rule wiring is added.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: Literal["critical", "warning", "advisory"] = "warning"
    references: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CuratedKnowledgePack(BaseModel):
    """Typed container for all curated design/rule packs."""

    styles: list[DesignKnowledgeItem] = Field(default_factory=list)
    palettes: list[DesignKnowledgeItem] = Field(default_factory=list)
    typography: list[DesignKnowledgeItem] = Field(default_factory=list)
    patterns: list[DesignKnowledgeItem] = Field(default_factory=list)
    products: list[DesignKnowledgeItem] = Field(default_factory=list)
    web_critical_rules: list[RuleKnowledgeItem] = Field(default_factory=list)
    web_warning_rules: list[RuleKnowledgeItem] = Field(default_factory=list)
    react_perf_rules: list[RuleKnowledgeItem] = Field(default_factory=list)


TModel = TypeVar("TModel", bound=BaseModel)


class KnowledgePackLoader:
    """
    Loader for curated knowledge JSON files under backend/knowledge.
    This loader is intentionally standalone and not wired into runtime yet.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parent

    def load_design_styles(self) -> list[DesignKnowledgeItem]:
        return self._load_typed_list("design/styles.json", DesignKnowledgeItem)

    def load_design_palettes(self) -> list[DesignKnowledgeItem]:
        return self._load_typed_list("design/palettes.json", DesignKnowledgeItem)

    def load_design_typography(self) -> list[DesignKnowledgeItem]:
        return self._load_typed_list("design/typography.json", DesignKnowledgeItem)

    def load_design_patterns(self) -> list[DesignKnowledgeItem]:
        return self._load_typed_list("design/patterns.json", DesignKnowledgeItem)

    def load_design_products(self) -> list[DesignKnowledgeItem]:
        return self._load_typed_list("design/products.json", DesignKnowledgeItem)

    def load_web_critical_rules(self) -> list[RuleKnowledgeItem]:
        return self._load_typed_list("rules/web_critical_rules.json", RuleKnowledgeItem)

    def load_web_warning_rules(self) -> list[RuleKnowledgeItem]:
        return self._load_typed_list("rules/web_warning_rules.json", RuleKnowledgeItem)

    def load_react_perf_rules(self) -> list[RuleKnowledgeItem]:
        return self._load_typed_list("rules/react_perf_rules.json", RuleKnowledgeItem)

    def load_all(self) -> CuratedKnowledgePack:
        return CuratedKnowledgePack(
            styles=self.load_design_styles(),
            palettes=self.load_design_palettes(),
            typography=self.load_design_typography(),
            patterns=self.load_design_patterns(),
            products=self.load_design_products(),
            web_critical_rules=self.load_web_critical_rules(),
            web_warning_rules=self.load_web_warning_rules(),
            react_perf_rules=self.load_react_perf_rules(),
        )

    def _load_typed_list(self, relative_path: str, model_type: type[TModel]) -> list[TModel]:
        path = self.root / relative_path
        payload = self._load_json_list(path)
        validated: list[TModel] = []

        for idx, item in enumerate(payload):
            if not isinstance(item, dict):
                raise KnowledgeFormatError(path, f"entry at index {idx} must be a JSON object")
            try:
                validated.append(model_type.model_validate(item))
            except ValidationError as exc:
                raise KnowledgeValidationError(path, idx, exc.errors()[0]["msg"]) from exc

        return validated

    def _load_json_list(self, path: Path) -> list[Any]:
        if not path.exists():
            raise KnowledgeFileNotFoundError(path)

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise KnowledgeLoaderError(f"Unable to read knowledge file {path}: {exc}") from exc

        try:
            payload = json.loads(raw or "[]")
        except json.JSONDecodeError as exc:
            raise KnowledgeFormatError(path, f"invalid JSON ({exc.msg})") from exc

        if not isinstance(payload, list):
            raise KnowledgeFormatError(path, "top-level JSON value must be a list")

        return payload


def load_curated_knowledge(root: Path | None = None) -> CuratedKnowledgePack:
    """Convenience helper used by future consumers."""
    return KnowledgePackLoader(root=root).load_all()
