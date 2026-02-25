import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path so `backend.*` imports work
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import ValidationError

from backend.core.setting import get_settings
from backend.emitter.react_codegen import (
    deterministic_antd_fallback,
    generate_react_from_compiled_ir,
)
from backend.ir.models import CompiledIRBundle


def _load_compiled_ir(path: Path) -> CompiledIRBundle:
    data = json.loads(path.read_text(encoding="utf-8"))
    return CompiledIRBundle.model_validate(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert compiled IR JSON to Ant Design React TSX using an LLM.")
    parser.add_argument("--input", default="compiled_ir.json", help="Path to compiled IR JSON file.")
    parser.add_argument("--output", default="generated_app.tsx", help="Path to output TSX file.")
    parser.add_argument("--model", default=None, help="LLM model name override.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    try:
        compiled = _load_compiled_ir(input_path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {input_path}: {exc}") from exc
    except ValidationError as exc:
        raise ValueError(f"JSON does not match CompiledIRBundle schema: {exc}") from exc

    settings = get_settings()
    model = args.model or settings.emitter_model

    try:
        tsx = generate_react_from_compiled_ir(
            compiled,
            model=model,
            temperature=settings.emitter_temperature,
            max_tokens=settings.emitter_max_tokens,
            provider=settings.llm_primary_provider,
            settings=settings,
        )
    except Exception as exc:
        tsx = deterministic_antd_fallback(compiled, error=str(exc))

    output_path = Path(args.output)
    output_path.write_text(tsx, encoding="utf-8")
    print(f"React code written to: {output_path.resolve()}")


if __name__ == "__main__":
    main()
