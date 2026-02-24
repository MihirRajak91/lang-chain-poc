# api/routes.py

from fastapi             import APIRouter, HTTPException
from pydantic            import BaseModel
from typing              import Literal
from backend.core.logger import get_logger
from backend.core.setting import get_settings
from backend.core.session import (
    get_session,
    save_session,
    save_compiled_ir,
    get_compiled_ir,
    clear_session,
    session_exists,
)
from backend.agents.conversation.models import UIPlan
from backend.agents.conversation.validators import evaluate_quality_gate
from backend.emitter.audit import EmitAuditReport, build_emit_audit_report
from backend.emitter.react_codegen import (
    deterministic_antd_fallback,
    generate_react_from_compiled_ir,
)
from backend.ir.compiler import IRCompiler

logger = get_logger(__name__)
router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class IngestDDLRequest(BaseModel):
    session_id: str
    ddl:        str

class IngestDDLResponse(BaseModel):
    session_id: str
    tables:     list[str]
    ui_hints:   dict

class CompileRequest(BaseModel):
    session_id: str

class CompileResponse(BaseModel):
    class CompileMetadataResponse(BaseModel):
        ir_version: str
        generated_at: str
        warnings: list[str]
        autofixes: list[str]
        gate_mode: Literal["hybrid", "hard", "advisory"]

    session_id:       str
    component_tree:   dict
    layout:           dict
    data:             dict
    behavior:         dict
    metadata:         CompileMetadataResponse

class EmitRequest(BaseModel):
    session_id: str

class EmitResponse(BaseModel):
    session_id: str
    files:      dict[str, str]   # filename → file content
    audit_report: EmitAuditReport

class PatchRequest(BaseModel):
    session_id: str
    op:         str              # "layout.update" | "component.update" | etc.
    target:     str              # node id
    path:       str              # dotted path within the IR
    value:      dict | str | int | float

class PatchResponse(BaseModel):
    session_id: str
    applied:    bool
    message:    str

class SessionStatusResponse(BaseModel):
    class QualitySummary(BaseModel):
        gate_mode: Literal["hybrid", "hard", "advisory"]
        is_blocked: bool
        critical_count: int
        warning_count: int
        blocking_count: int
        critical_violations: list[str]
        warning_findings: list[str]
        blocking_findings: list[str]

    session_id:   str
    mode:         str
    missing:      list[str]
    guideline_violations: list[str]
    quality:      QualitySummary
    confirmed:    bool
    active_agent: str | None
    turns:        int

class ResetResponse(BaseModel):
    session_id: str
    reset:      bool


# ── POST /api/ingest-ddl ──────────────────────────────────────────────────────

@router.post("/ingest-ddl", response_model=IngestDDLResponse)
async def ingest_ddl(req: IngestDDLRequest):
    """
    Parses the SQL DDL and stores NormalizedSchema + UIHints on the session.
    Sprint 1 — Schema Analyst agent.
    """
    logger.info("Ingesting DDL for session: %s", req.session_id)

    try:
        # TODO Sprint 1: wire schema analyst
        # from schema.parser       import parse_ddl
        # from schema.normalizer   import normalize
        # from schema.intelligence import infer_hints
        #
        # ast    = parse_ddl(req.ddl)
        # schema = normalize(ast)
        # hints  = infer_hints(schema)
        #
        # state = get_session(req.session_id)
        # state.normalized_schema = schema
        # state.ui_hints          = hints
        # save_session(req.session_id, state)
        #
        # return IngestDDLResponse(
        #     session_id = req.session_id,
        #     tables     = [t.name for t in schema.tables],
        #     ui_hints   = hints.model_dump(),
        # )

        # POC placeholder
        return IngestDDLResponse(
            session_id = req.session_id,
            tables     = ["placeholder — wire schema analyst in Sprint 1"],
            ui_hints   = {},
        )

    except Exception as e:
        logger.error("DDL ingestion failed: %s", e)
        raise HTTPException(status_code=422, detail=str(e))


# ── POST /api/compile ─────────────────────────────────────────────────────────

@router.post("/compile", response_model=CompileResponse)
async def compile_ir(req: CompileRequest):
    """
    Compiles confirmed UIPlan → 4 sub-IRs.
    Requires session to be in 'done' mode (conversation confirmed).
    Sprint 2 — IR Compiler.
    """
    logger.info("Compiling IR for session: %s", req.session_id)

    if not session_exists(req.session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    state = get_session(req.session_id)
    settings = get_settings()
    gate = evaluate_quality_gate(
        state.fields,
        gate_mode=settings.quality_gate_mode,
    )
    missing_slots = state.missing
    blocking_findings = [item.message for item in gate.blocking_findings]

    if (not state.confirmed) or missing_slots or blocking_findings:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "compile_blocked",
                "missing_slots": missing_slots,
                "blocking_findings": blocking_findings,
                "gate_mode": gate.gate_mode,
            },
        )

    try:
        ui_plan = UIPlan.from_spec(state.fields)
        compiled = IRCompiler().compile(ui_plan, gate_mode=gate.gate_mode)
        payload = compiled.model_dump(exclude_none=True)
        save_compiled_ir(req.session_id, payload)

        return CompileResponse(
            session_id     = req.session_id,
            component_tree = payload["component_tree"],
            layout         = payload["layout"],
            data           = payload["data"],
            behavior       = payload["behavior"],
            metadata       = payload["metadata"],
        )

    except Exception as e:
        logger.error("IR compilation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /api/emit ────────────────────────────────────────────────────────────

@router.post("/emit", response_model=EmitResponse)
async def emit_code(req: EmitRequest):
    """
    Runs LLM Emitter against compiled sub-IRs → TSX + types.ts + api.ts.
    Sprint 3 — LLM Emitter agent.
    """
    logger.info("Emitting code for session: %s", req.session_id)

    if not session_exists(req.session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        state = get_session(req.session_id)
        settings = get_settings()

        # TODO Sprint 3: wire emitter agent
        # from agents.emitter import EmitterAgent
        # files = await EmitterAgent().emit(sub_irs)
        #
        # return EmitResponse(
        #     session_id = req.session_id,
        #     files      = files,   # { "Page.tsx": "...", "types.ts": "...", "api.ts": "..." }
        #     audit_report = build_emit_audit_report(...),
        # )

        audit_report = build_emit_audit_report(
            state.fields,
            gate_mode=settings.quality_gate_mode,
            enabled=settings.react_quality_audit_enabled,
        )

        compiled_ir = get_compiled_ir(req.session_id)
        page_tsx: str
        if compiled_ir is None:
            logger.warning(
                "Compiled IR missing for session %s; returning placeholder file.",
                req.session_id,
            )
            page_tsx = (
                "// No compiled IR found for this session.\n"
                "// Run POST /api/compile before /api/emit.\n"
            )
        else:
            try:
                page_tsx = generate_react_from_compiled_ir(
                    compiled_ir,
                    model=getattr(settings, "emitter_model", "gpt-4o"),
                    api_key=getattr(settings, "openai_api_key", None),
                    temperature=getattr(settings, "emitter_temperature", 0.0),
                    max_tokens=getattr(settings, "emitter_max_tokens", 4096),
                )
            except Exception as exc:
                logger.warning(
                    "LLM emit generation failed for session %s, using deterministic fallback: %s",
                    req.session_id,
                    exc,
                )
                page_tsx = deterministic_antd_fallback(compiled_ir, error=str(exc))

        return EmitResponse(
            session_id = req.session_id,
            files      = {"Page.tsx": page_tsx},
            audit_report = audit_report,
        )

    except Exception as e:
        logger.error("Code emission failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /api/patch ───────────────────────────────────────────────────────────

@router.post("/patch", response_model=PatchResponse)
async def apply_patch(req: PatchRequest):
    """
    Classifies + applies an incremental patch to the relevant sub-IR.
    Sprint 4 — Patch Classifier agent.
    """
    logger.info(
        "Patch request for session: %s | op: %s | target: %s",
        req.session_id, req.op, req.target,
    )

    if not session_exists(req.session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        # TODO Sprint 4: wire patch classifier
        # from agents.patch_classifier import PatchClassifier
        # from ir.patch import apply_patch
        #
        # patch  = PatchClassifier().classify(req.op, req.target, req.path, req.value)
        # result = apply_patch(session_sub_irs, patch)
        #
        # return PatchResponse(
        #     session_id = req.session_id,
        #     applied    = result.success,
        #     message    = result.message,
        # )

        # POC placeholder
        return PatchResponse(
            session_id = req.session_id,
            applied    = False,
            message    = "Patch classifier not yet wired — Sprint 4",
        )

    except Exception as e:
        logger.error("Patch failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /api/session/{session_id} ─────────────────────────────────────────────

@router.get("/session/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str):
    """
    Returns current session state — useful for frontend debug panel.
    """
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    state = get_session(session_id)
    settings = get_settings()

    gate = evaluate_quality_gate(
        state.fields,
        gate_mode=settings.quality_gate_mode,
    )
    critical_messages = [item.message for item in gate.critical_violations]
    warning_messages = [item.message for item in gate.warning_findings]
    blocking_messages = [item.message for item in gate.blocking_findings]

    return SessionStatusResponse(
        session_id   = session_id,
        mode         = state.mode,
        missing      = state.missing,
        guideline_violations = blocking_messages,
        quality      = SessionStatusResponse.QualitySummary(
            gate_mode = gate.gate_mode,
            is_blocked = gate.is_blocked,
            critical_count = len(gate.critical_violations),
            warning_count = len(gate.warning_findings),
            blocking_count = len(gate.blocking_findings),
            critical_violations = critical_messages,
            warning_findings = warning_messages,
            blocking_findings = blocking_messages,
        ),
        confirmed    = state.confirmed,
        active_agent = state.active_agent,
        turns        = state.free_chat_turns(),
    )


# ── DELETE /api/session/{session_id} ─────────────────────────────────────────

@router.delete("/session/{session_id}", response_model=ResetResponse)
async def reset_session(session_id: str):
    """
    Clears session — lets user start over.
    """
    clear_session(session_id)
    return ResetResponse(session_id=session_id, reset=True)
