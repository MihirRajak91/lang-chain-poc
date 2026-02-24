# api/routes.py

from fastapi             import APIRouter, HTTPException
from pydantic            import BaseModel
from backend.core.logger import get_logger
from backend.core.session import (
    get_session,
    save_session,
    clear_session,
    session_exists,
)

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
    session_id:       str
    component_tree:   dict
    layout:           dict
    data:             dict
    behavior:         dict

class EmitRequest(BaseModel):
    session_id: str

class EmitResponse(BaseModel):
    session_id: str
    files:      dict[str, str]   # filename → file content

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
    session_id:   str
    mode:         str
    missing:      list[str]
    guideline_violations: list[str]
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

    if not state.confirmed:
        raise HTTPException(
            status_code=400,
            detail="UIPlan not yet confirmed. Complete the conversation first."
        )

    try:
        # TODO Sprint 2: wire IR compiler
        # from ir.compiler import IRCompiler
        # ui_plan   = UIPlan.from_fields(state.fields)
        # sub_irs   = IRCompiler().compile(ui_plan)
        # save_session(req.session_id, state)
        #
        # return CompileResponse(
        #     session_id     = req.session_id,
        #     component_tree = sub_irs.component_tree.model_dump(),
        #     layout         = sub_irs.layout.model_dump(),
        #     data           = sub_irs.data.model_dump(),
        #     behavior       = sub_irs.behavior.model_dump(),
        # )

        # POC placeholder
        return CompileResponse(
            session_id     = req.session_id,
            component_tree = {},
            layout         = {},
            data           = {},
            behavior       = {},
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
        # TODO Sprint 3: wire emitter agent
        # from agents.emitter import EmitterAgent
        # files = await EmitterAgent().emit(sub_irs)
        #
        # return EmitResponse(
        #     session_id = req.session_id,
        #     files      = files,   # { "Page.tsx": "...", "types.ts": "...", "api.ts": "..." }
        # )

        # POC placeholder
        return EmitResponse(
            session_id = req.session_id,
            files      = {"Page.tsx": "// placeholder — wire emitter in Sprint 3"},
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

    return SessionStatusResponse(
        session_id   = session_id,
        mode         = state.mode,
        missing      = state.missing,
        guideline_violations = state.guideline_violations,
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
