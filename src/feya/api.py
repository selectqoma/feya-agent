from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from temporalio.client import Client

from feya import db as tables
from feya.config import Settings, settings
from feya.db import make_engine, scope
from feya.domain import CaseCommand, Decision, Fault, Inbound, Proposal, uid
from feya.gateway import FakeProvider
from feya.packs import load_packs
from feya.service import Conflict, Denied, NotFound, Service


def create_app(config: Settings = settings, service: Service | None = None):
    # shortcut: fixed loopback-only identity, replace with OIDC and DB grants before customer use.
    if not config.local_demo:
        raise RuntimeError(
            "Production identity is not implemented; local synthetic deployment only"
        )
    app = FastAPI(title="Feya", version="0.1.0")
    s = service or Service(
        make_engine(config.database_url), load_packs(config.pack_dir), config.tenant_id
    )
    app.state.service = s

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse({"detail": "Local workspace only"}, 403)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin requests are not accepted"}, 403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("x-feya-local") != "1":
                return JSONResponse({"detail": "Local operation header required"}, 403)
            try:
                body = await request.body()
            except Exception:
                return JSONResponse({"detail": "Invalid request body"}, 400)
            if len(body) > 32768:
                return JSONResponse({"detail": "Request is too large"}, 413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    @app.exception_handler(ValueError)
    async def validation_error(request: Request, exc: ValueError):
        status = (
            404
            if isinstance(exc, NotFound)
            else 403
            if isinstance(exc, Denied)
            else 409
            if isinstance(exc, Conflict)
            else 422
        )
        return JSONResponse({"detail": str(exc)}, status)

    @app.get("/health")
    def health():
        with s.engine.connect() as db:
            db.execute(select(1))
        return {"status": "ok", "mode": "local-synthetic"}

    @app.get("/v1/workspace")
    async def workspace():
        with s.engine.connect() as db:
            backlog = db.execute(
                select(func.count())
                .select_from(tables.outbox)
                .where(scope(tables.outbox, s.tenant), tables.outbox.c.processed.is_(False))
            ).scalar_one()
        try:
            client = await Client.connect(config.temporal_address)
            await client.service_client.check_health()
            temporal = "connected"
        except Exception:
            temporal = "unavailable"
        return {
            "name": "Feya Studio",
            "tenant_id": s.tenant,
            "identity": "local-operator",
            "role": "approver",
            "mode": "local-synthetic",
            "runner": config.runner,
            "model": config.model or "fixture:deterministic-v1",
            "temporal": temporal,
            "backlog": backlog,
            "dispatch": "disabled",
            "packs": [p.model_dump() | {"fingerprint": p.fingerprint} for p in s.packs.values()],
        }

    @app.get("/v1/cases")
    def cases(phase: str | None = None, limit: int = Query(100, ge=1, le=200)):
        return s.list_cases(phase, limit)

    @app.get("/v1/cases/{case_id}")
    def detail(case_id: str):
        return s.detail(case_id)

    @app.get("/v1/cases/{case_id}/export")
    def export(case_id: str):
        return JSONResponse(
            s.detail(case_id),
            headers={"Content-Disposition": f'attachment; filename="{case_id}.json"'},
        )

    @app.post("/v1/ingest", status_code=202)
    def ingest(event: Inbound):
        return s.ingest(event)

    @app.post("/v1/demo/{pack_id}", status_code=202)
    def demo(pack_id: str):
        if pack_id not in s.packs:
            raise HTTPException(404, "Unknown pack")
        pack = s.packs[pack_id]
        return s.ingest(
            Inbound(
                event_id=uid("demo"),
                thread_id=uid("thread"),
                pack_id=pack.id,
                sender=pack.fixture["sender"],
                subject=pack.fixture["subject"],
                body=pack.fixture["body"],
            )
        )

    @app.post("/v1/cases/{case_id}/demo-reply", status_code=202)
    def reply(case_id: str):
        case = s.detail(case_id)
        pack = s.packs[case["pack_id"]]
        return s.ingest(
            Inbound(
                event_id=uid("demo"),
                thread_id=case["thread_id"],
                pack_id=pack.id,
                sender=case["customer_email"],
                subject="Re: " + case["subject"],
                body=pack.fixture["reply"],
            )
        )

    @app.post("/v1/cases/{case_id}/actions", status_code=201)
    def propose(case_id: str, proposal: Proposal):
        return s.propose(case_id, proposal)

    @app.post("/v1/approvals/{intent_id}/decide", status_code=202)
    def decide(intent_id: str, decision: Decision):
        return s.decide(intent_id, decision)

    @app.post("/v1/action-intents/{intent_id}/{operation}", status_code=202)
    def operation(intent_id: str, operation: str):
        if operation not in {"commit", "reconcile"}:
            raise HTTPException(404, "Unknown operation")
        return s.request_operation(intent_id, operation)

    @app.post("/v1/demo/faults/{intent_id}")
    def fault(intent_id: str, fault: Fault):
        with s.engine.connect() as db:
            intent = s.row(db, tables.intents, intent_id)
            if intent["status"] not in {"ready", "awaiting_approval"}:
                raise Conflict("Faults can only be configured before an attempt")
        FakeProvider(s.engine, s.tenant).set_fault(intent_id, fault.mode)
        return {"mode": fault.mode}

    @app.post("/v1/cases/{case_id}/retry", status_code=202)
    def retry(case_id: str):
        return s.retry(case_id)

    @app.post("/v1/cases/{case_id}/{command}")
    def command(case_id: str, command: str, data: CaseCommand):
        if command not in {"cancel", "complete-manually"}:
            raise HTTPException(404, "Unknown case operation")
        return s.command(
            case_id, data, "case.cancelled" if command == "cancel" else "case.manual_completed"
        )

    console = Path(config.console_dir)
    if (console / "assets").exists():
        app.mount("/assets", StaticFiles(directory=console / "assets"), name="assets")

    @app.get("/")
    def index():
        if not (console / "index.html").exists():
            return {
                "message": "Build the console: cd apps/console && npm ci && npm run build",
                "api": "/docs",
            }
        return FileResponse(console / "index.html")

    return app
