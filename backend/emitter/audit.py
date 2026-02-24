from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.agents.conversation.models import RequirementSpec
from backend.agents.conversation.validators import evaluate_quality_gate


class AuditFinding(BaseModel):
    severity: Literal["critical", "warning"]
    slot: str
    message: str
    blocking: bool


class EmitAuditReport(BaseModel):
    """
    Deterministic emitter-audit stub.
    This report is returned by the emit API while the real emitter audit is pending.
    """

    engine: Literal["deterministic_stub", "disabled"] = "deterministic_stub"
    gate_mode: Literal["hybrid", "hard", "advisory"] = "hybrid"
    blocked: bool = False
    passed: bool = True
    critical_count: int = 0
    warning_count: int = 0
    blocking_count: int = 0
    findings: list[AuditFinding] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def build_emit_audit_report(
    spec: RequirementSpec,
    gate_mode: Literal["hybrid", "hard", "advisory"] = "hybrid",
    enabled: bool = True,
) -> EmitAuditReport:
    if not enabled:
        return EmitAuditReport(
            engine="disabled",
            gate_mode=gate_mode,
            notes=["Emitter audit disabled by configuration."],
        )

    gate = evaluate_quality_gate(spec, gate_mode=gate_mode)
    blocking_keys = {
        (item.severity, item.slot, item.message)
        for item in gate.blocking_findings
    }

    findings: list[AuditFinding] = []
    for issue in [*gate.critical_violations, *gate.warning_findings]:
        key = (issue.severity, issue.slot, issue.message)
        findings.append(
            AuditFinding(
                severity=issue.severity,
                slot=issue.slot,
                message=issue.message,
                blocking=key in blocking_keys,
            )
        )

    return EmitAuditReport(
        engine="deterministic_stub",
        gate_mode=gate.gate_mode,
        blocked=gate.is_blocked,
        passed=not gate.is_blocked,
        critical_count=len(gate.critical_violations),
        warning_count=len(gate.warning_findings),
        blocking_count=len(gate.blocking_findings),
        findings=findings,
        notes=[
            "Deterministic audit stub; replace with emitter-native quality audit in a later step."
        ],
    )
