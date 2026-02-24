from __future__ import annotations

import json
import re
from typing import Any

from langchain_openai import ChatOpenAI

from backend.ir.models import CompiledIRBundle


def extract_code_block(text: str) -> str:
    match = re.search(r"```(?:tsx|jsx|typescript|javascript)?\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def build_antd_prompt(ir_json: str) -> str:
    return f"""
You are a senior React engineer.
Convert the provided compiled IR JSON into a complete React component file in TypeScript.

Output requirements:
- Return TSX code only. No markdown and no extra text.
- Export default function GeneratedApp().
- Use Ant Design components for UI (antd).
- Do not import any UI library other than antd and React.

Implementation requirements:
- The IR shape is:
  - component_tree: {{ root_id, nodes[] }}
  - layout: {{ strategy, breakpoints, zones[] }}
  - data: {{ entities[] }}
  - behavior: {{ interactions[], constraints[] }}
  - metadata: {{ ... }}
- Build state using behavior and data when useful.
- Build one handler per behavior.interactions[].action_id.
- If a component has matching handler ids in behavior (action_id), wire onClick.
- Respect layout zones and anchors:
  - base zones render in normal flow.
  - overlay zones render with antd Modal when component type suggests modal/dialog.
- Respect component kinds:
  - DataTable -> antd Table
  - PrimaryButton/Button -> antd Button
  - Modal/Dialog -> antd Modal
  - Card -> antd Card
  - Form -> antd Form
- Unknown component kinds must render fallback:
  <div>Unsupported component: {{kind}}</div>
- Use component props from node.props and render labels where available.
- Keep code robust and compile-ready TypeScript.

IR JSON:
{ir_json}
""".strip()


def generate_react_from_compiled_ir(
    ir_bundle: CompiledIRBundle | dict[str, Any],
    *,
    model: str = "gpt-5.2",
    api_key: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> str:
    bundle = (
        ir_bundle
        if isinstance(ir_bundle, CompiledIRBundle)
        else CompiledIRBundle.model_validate(ir_bundle)
    )

    prompt = build_antd_prompt(bundle.model_dump_json(indent=2))
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key,
        max_tokens=max_tokens,
    )
    response = llm.invoke(prompt)
    raw = response.content if isinstance(response.content, str) else str(response.content)
    code = extract_code_block(raw)
    return code if code.endswith("\n") else f"{code}\n"


def deterministic_antd_fallback(ir_bundle: CompiledIRBundle | dict[str, Any], *, error: str | None = None) -> str:
    bundle = (
        ir_bundle
        if isinstance(ir_bundle, CompiledIRBundle)
        else CompiledIRBundle.model_validate(ir_bundle)
    )

    note = f"// emitter fallback reason: {error}\n" if error else ""
    entities = bundle.data.entities
    interactions = bundle.behavior.interactions

    columns_block = "[]"
    if entities and entities[0].fields:
        cols = [{"title": field, "dataIndex": field, "key": field} for field in entities[0].fields]
        columns_block = json.dumps(cols, indent=2)

    return (
        "import React from 'react';\n"
        "import { Alert, Button, Card, ConfigProvider, Space, Table, Typography } from 'antd';\n\n"
        f"{note}"
        "const columns = "
        f"{columns_block} as const;\n\n"
        "const dataSource: Record<string, unknown>[] = [];\n\n"
        "export default function GeneratedApp() {\n"
        "  return (\n"
        "    <ConfigProvider>\n"
        "      <Space direction=\"vertical\" size={16} style={{ width: '100%', padding: 24 }}>\n"
        "        <Typography.Title level={3}>Generated UI (Fallback)</Typography.Title>\n"
        "        <Alert\n"
        "          type=\"warning\"\n"
        "          showIcon\n"
        "          message=\"LLM emitter unavailable; rendering deterministic Ant Design fallback.\"\n"
        "        />\n"
        "        <Card title=\"Data Preview\">\n"
        "          <Table columns={columns as any} dataSource={dataSource} pagination={false} rowKey=\"id\" />\n"
        "        </Card>\n"
        "        <Card title=\"Interactions\">\n"
        "          <Space wrap>\n"
        + "".join(
            f"            <Button key=\"{item.action_id}\">{item.action_id}</Button>\n"
            for item in interactions
        )
        + "          </Space>\n"
        "        </Card>\n"
        "      </Space>\n"
        "    </ConfigProvider>\n"
        "  );\n"
        "}\n"
    )
