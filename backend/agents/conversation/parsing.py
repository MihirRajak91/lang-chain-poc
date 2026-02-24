from __future__ import annotations

import json
import re


def strip_json_fences(raw: str) -> str:
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if not lines:
        return text

    # Remove opening fence and optional language marker.
    body = lines[1:] if lines[0].startswith("```") else lines
    text = "\n".join(body).strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    if text.lower().startswith("json"):
        text = text[4:].strip()

    return text


def extract_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False

    for idx in range(start, len(text)):
        ch = text[idx]

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]

    return None


def _normalize_jsonish(text: str) -> str:
    normalized = text

    # Normalize smart quotes that often appear in chat output.
    normalized = (
        normalized
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )

    # Remove trailing commas before object/array close.
    normalized = re.sub(r",\s*([}\]])", r"\1", normalized)
    return normalized


def parse_json_object_with_fallback(raw: str) -> dict | None:
    """
    Best-effort extractor for model JSON output.
    Returns a dict or None if no valid JSON object can be recovered.
    """
    stripped = strip_json_fences(raw)
    extracted = extract_balanced_json_object(stripped)

    candidates: list[str] = [stripped]
    if extracted and extracted not in candidates:
        candidates.append(extracted)

    normalized_variants: list[str] = []
    for candidate in list(candidates):
        normalized = _normalize_jsonish(candidate)
        if normalized not in candidates and normalized not in normalized_variants:
            normalized_variants.append(normalized)

    candidates.extend(normalized_variants)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    return None
