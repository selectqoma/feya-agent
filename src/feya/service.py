from datetime import date, timedelta

from sqlalchemy import select, text, update

from feya import db as tables
from feya.db import json_row, scope
from feya.domain import (
    AgentResult,
    AgentTask,
    CaseCommand,
    Decision,
    Inbound,
    Proposal,
    digest,
    now,
    transition,
    uid,
)
from feya.packs import BusinessPack
from feya.policy import action_digest, evaluate


class Conflict(ValueError):
    pass


class NotFound(ValueError):
    pass


class Denied(ValueError):
    pass


class Service:
    def __init__(self, engine, packs: dict[str, BusinessPack], tenant: str):
        self.engine, self.packs, self.tenant = engine, packs, tenant

    def row(self, db, table, object_id: str, *, lock=False):
        query = select(table).where(scope(table, self.tenant, object_id))
        if lock:
            query = query.with_for_update()
        row = db.execute(query).mappings().first()
        if row is None:
            raise NotFound("Object not found in this workspace")
        return dict(row)

    def sources(self, db, case_id: str) -> list[dict]:
        return [
            dict(r)
            for r in db.execute(
                select(tables.evidence)
                .where(scope(tables.evidence, self.tenant), tables.evidence.c.case_id == case_id)
                .order_by(tables.evidence.c.revision)
            ).mappings()
        ]

    def record(self, db, case: dict, kind: str, actor: str, detail: dict):
        db.execute(
            tables.audit.insert().values(
                tenant_id=self.tenant,
                id=uid("evt"),
                case_id=case["id"],
                kind=kind,
                actor=actor,
                case_version=case["version"],
                detail=detail,
            )
        )

    def change(
        self, db, case: dict, kind: str, actor="worker", *, verified=False, reason="", **values
    ):
        values["phase"] = transition(case["phase"], kind, verified=verified, reason=reason)
        values["version"] = case["version"] + 1
        result = db.execute(
            update(tables.cases)
            .where(
                scope(tables.cases, self.tenant, case["id"]),
                tables.cases.c.version == case["version"],
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise Conflict("Case changed; refresh before continuing")
        case.update(values)
        self.record(db, case, kind, actor, {"reason": reason, "phase": values["phase"]})

    def queue(self, db, case: dict, kind: str, payload: dict):
        event_id = uid("job")
        db.execute(
            tables.outbox.insert().values(
                tenant_id=self.tenant, id=event_id, case_id=case["id"], kind=kind, payload=payload
            )
        )
        return event_id

    def ingest(self, inbound: Inbound) -> dict:
        if inbound.pack_id not in self.packs:
            raise ValueError("Unknown business pack")
        pack = self.packs[inbound.pack_id]
        with self.engine.begin() as db:
            # Serialize event identity and thread creation even for concurrent duplicate webhooks.
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"{self.tenant}:ingestion"},
            )
            prior = (
                db.execute(
                    select(tables.evidence).where(
                        scope(tables.evidence, self.tenant),
                        tables.evidence.c.event_id == inbound.event_id,
                    )
                )
                .mappings()
                .first()
            )
            content = inbound.model_dump()
            if prior:
                if prior["content_hash"] != digest(content):
                    raise Conflict("Event ID was already used with different content")
                return {"case_id": prior["case_id"], "deduplicated": True}
            current = (
                db.execute(
                    select(tables.cases)
                    .where(
                        scope(tables.cases, self.tenant),
                        tables.cases.c.thread_id == inbound.thread_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if current:
                case = dict(current)
                if case["customer_email"] != inbound.sender or case["pack_id"] != inbound.pack_id:
                    raise Conflict("Thread identity changed; human correlation is required")
                if case["phase"] in {
                    "executing",
                    "verify_pending",
                    "reconciliation_required",
                    "cancelled",
                }:
                    raise Conflict(
                        "Resolve or cancel the outstanding operation before adding evidence"
                    )
                self.change(
                    db,
                    case,
                    "source.recorded",
                    "ingress",
                    source_revision=case["source_revision"] + 1,
                    next_action="Analyse the new reply",
                    completion_kind=None,
                )
                db.execute(
                    update(tables.intents)
                    .where(
                        scope(tables.intents, self.tenant),
                        tables.intents.c.case_id == case["id"],
                        tables.intents.c.status.in_(["ready", "awaiting_approval", "denied"]),
                    )
                    .values(status="superseded")
                )
                db.execute(
                    update(tables.approvals)
                    .where(
                        scope(tables.approvals, self.tenant),
                        tables.approvals.c.case_id == case["id"],
                        tables.approvals.c.consumed_at.is_(None),
                    )
                    .values(revoked_at=now())
                )
            else:
                case = dict(
                    tenant_id=self.tenant,
                    id=uid("case"),
                    thread_id=inbound.thread_id,
                    pack_id=pack.id,
                    pack_hash=pack.fingerprint,
                    customer_email=inbound.sender,
                    subject=inbound.subject,
                    phase="new",
                    version=1,
                    source_revision=1,
                    summary="",
                    facts={},
                    missing=[f.key for f in pack.required_facts],
                    next_action="Analyse the enquiry",
                )
                db.execute(tables.cases.insert().values(**case))
                self.record(db, case, "case.created", "ingress", {"pack_id": pack.id})
            evidence_id = uid("src")
            db.execute(
                tables.evidence.insert().values(
                    tenant_id=self.tenant,
                    id=evidence_id,
                    case_id=case["id"],
                    event_id=inbound.event_id,
                    external_object_id=inbound.thread_id,
                    source_uri=f"fake-email://{inbound.thread_id}/{inbound.event_id}",
                    content=content,
                    content_hash=digest(content),
                    revision=case["source_revision"],
                )
            )
            self.record(db, case, "evidence.recorded", "ingress", {"evidence_id": evidence_id})
            self.queue(db, case, "triage", {"source_revision": case["source_revision"]})
            return {"case_id": case["id"], "deduplicated": False}

    def list_cases(self, phase: str | None = None, limit: int = 100):
        with self.engine.connect() as db:
            query = select(tables.cases).where(scope(tables.cases, self.tenant))
            if phase:
                query = query.where(tables.cases.c.phase == phase)
            return [
                json_row(r)
                for r in db.execute(
                    query.order_by(tables.cases.c.created_at.desc()).limit(limit)
                ).mappings()
            ]

    def detail(self, case_id: str) -> dict:
        with self.engine.connect() as db:
            case = json_row(self.row(db, tables.cases, case_id))
            for name, table in [
                ("evidence", tables.evidence),
                ("timeline", tables.audit),
                ("actions", tables.intents),
                ("artifacts", tables.artifacts),
                ("runs", tables.runs),
                ("verifications", tables.verifications),
                ("approvals", tables.approvals),
            ]:
                case[name] = [
                    json_row(r)
                    for r in db.execute(
                        select(table)
                        .where(scope(table, self.tenant), table.c.case_id == case_id)
                        .order_by(table.c.created_at)
                    ).mappings()
                ]
            return case

    def agent_task(self, case_id: str, revision: int) -> AgentTask | None:
        with self.engine.connect() as db:
            case = self.row(db, tables.cases, case_id)
            if case["source_revision"] != revision or case["phase"] not in {"new", "blocked"}:
                return None
            pack = self.packs[case["pack_id"]]
            return AgentTask(
                tenant_id=self.tenant,
                case_id=case_id,
                required_fields=[f.key for f in pack.required_facts],
                evidence=[
                    {"id": s["id"], "body": s["content"]["body"]} for s in self.sources(db, case_id)
                ],
            )

    def apply_triage(self, task: AgentTask, result: AgentResult):
        with self.engine.begin() as db:
            case = self.row(db, tables.cases, task.case_id, lock=True)
            sources = self.sources(db, case["id"])
            if case["phase"] not in {"new", "blocked"} or {s["id"] for s in sources} != {
                e["id"] for e in task.evidence
            }:
                return
            pack = self.packs[case["pack_id"]]
            if case["pack_hash"] != pack.fingerprint:
                raise Conflict("Pack changed during reasoning")
            indexed = {s["id"]: s for s in sources}
            fields = {f.key: f for f in pack.required_facts}
            facts: dict[str, dict] = {}
            warnings = list(result.output.warnings)
            for claim in result.output.claims:
                source = indexed.get(claim.evidence_id)
                if (
                    claim.key not in fields
                    or source is None
                    or claim.quote not in source["content"]["body"]
                    or claim.value not in claim.quote
                ):
                    warnings.append("Unsupported claim omitted")
                    continue
                field = fields[claim.key]
                try:
                    if field.kind == "date":
                        date.fromisoformat(claim.value)
                    if field.kind == "quantity" and (
                        not claim.value.isascii()
                        or not claim.value.isdigit()
                        or not 1 <= int(claim.value) <= 999
                    ):
                        raise ValueError("Invalid quantity")
                    if field.kind == "service" and claim.value not in pack.rates:
                        raise ValueError("Unsupported service")
                except ValueError:
                    warnings.append(f"Invalid required fact: {claim.key}")
                    continue
                # Newer observations win; conflicting claims from the same observation need review.
                prior = facts.get(claim.key)
                if prior and indexed[prior["evidence_id"]]["revision"] > source["revision"]:
                    continue
                if (
                    prior
                    and prior["evidence_id"] == claim.evidence_id
                    and prior["value"] != claim.value
                ):
                    raise Conflict(f"Ambiguous source values for {claim.key}")
                facts[claim.key] = claim.model_dump()
            missing = [f.key for f in pack.required_facts if f.key not in facts]
            db.execute(
                tables.runs.insert().values(
                    tenant_id=self.tenant,
                    id=uid("run"),
                    case_id=case["id"],
                    role=task.role,
                    model=result.model,
                    prompt_version=task.prompt_version,
                    pack_hash=pack.fingerprint,
                    source_revision=case["source_revision"],
                    status="validated",
                    usage={
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "warning_count": len(warnings),
                        "tools": [],
                    },
                    evidence_ids=list(indexed),
                )
            )
            self.change(
                db,
                case,
                "triage.completed",
                summary=result.output.summary,
                facts=facts,
                missing=missing,
            )
            if missing:
                self.change(
                    db,
                    case,
                    "information.missing",
                    next_action="Review the information request; awaiting customer reply",
                )
                payload = {
                    "to": case["customer_email"],
                    "subject": "Re: " + case["subject"],
                    "body": pack.reply_intro
                    + "\n\n"
                    + "\n".join(f"• {fields[k].label}" for k in missing),
                }
                proposal = Proposal(
                    capability="email.draft.create", payload=payload, evidence_ids=list(indexed)
                )
            else:
                self.change(db, case, "information.sufficient")
                payload = pack.quote(
                    {k: v["value"] for k, v in facts.items()}, case["customer_email"]
                )
                self.change(db, case, "draft.created", next_action="Review the proposed offer")
                proposal = Proposal(
                    capability="accounting.offer.create_draft",
                    payload=payload,
                    evidence_ids=list(indexed),
                )
            self._propose(db, case, proposal)

    def _propose(self, db, case: dict, proposal: Proposal) -> dict:
        key = f"{case['id']}:{case['source_revision']}:{proposal.capability}"
        existing = (
            db.execute(
                select(tables.intents).where(
                    scope(tables.intents, self.tenant), tables.intents.c.idempotency_key == key
                )
            )
            .mappings()
            .first()
        )
        if existing:
            if existing["payload"] != proposal.payload:
                raise Conflict("An action exists for this operation; use the draft edit endpoint")
            return dict(existing)
        action = dict(
            tenant_id=self.tenant,
            id=uid("act"),
            case_id=case["id"],
            capability=proposal.capability,
            payload=proposal.payload,
            evidence_ids=sorted(proposal.evidence_ids),
            source_revision=case["source_revision"],
            pack_hash=case["pack_hash"],
            idempotency_key=key,
        )
        action["digest"] = action_digest(action)
        effect, reasons = evaluate(
            case, action, self.sources(db, case["id"]), self.packs[case["pack_id"]]
        )
        action.update(
            policy_effect=effect,
            policy_reasons=reasons,
            status={"allow": "ready", "require_approval": "awaiting_approval", "deny": "denied"}[
                effect
            ],
        )
        db.execute(tables.intents.insert().values(**action))
        db.execute(
            tables.artifacts.insert().values(
                tenant_id=self.tenant,
                id=uid("art"),
                case_id=case["id"],
                kind=proposal.capability,
                content=proposal.payload,
                content_hash=digest(proposal.payload),
                source_revision=case["source_revision"],
            )
        )
        self.record(
            db,
            case,
            "action.proposed",
            "policy",
            {"intent_id": action["id"], "effect": effect, "reasons": reasons},
        )
        if effect == "require_approval":
            self.change(db, case, "approval.requested")
        elif effect == "allow":
            self.queue(db, case, "commit", {"intent_id": action["id"]})
        return action

    def propose(self, case_id: str, proposal: Proposal):
        with self.engine.begin() as db:
            return json_row(
                self._propose(db, self.row(db, tables.cases, case_id, lock=True), proposal)
            )

    def decide(self, intent_id: str, decision: Decision, actor="local-operator", role="approver"):
        if role not in {"approver", "admin"}:
            raise Denied("An authenticated approver is required")
        with self.engine.begin() as db:
            initial = self.row(db, tables.intents, intent_id)
            case = self.row(db, tables.cases, initial["case_id"], lock=True)
            action = self.row(db, tables.intents, intent_id, lock=True)
            if (
                decision.expected_digest != action["digest"]
                or action_digest(action) != action["digest"]
            ):
                raise Conflict("The action changed; inspect the current proposal")
            existing = (
                db.execute(
                    select(tables.approvals).where(
                        scope(tables.approvals, self.tenant),
                        tables.approvals.c.intent_id == intent_id,
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                if existing["decision"] == decision.decision and not existing["revoked_at"]:
                    return {"status": action["status"], "deduplicated": True}
                raise Conflict("This decision was already recorded or revoked")
            if action["status"] != "awaiting_approval":
                raise Conflict("Action is no longer awaiting approval")
            effect, reasons = evaluate(
                case, action, self.sources(db, case["id"]), self.packs[case["pack_id"]]
            )
            if effect != "require_approval":
                raise Denied("; ".join(reasons))
            db.execute(
                tables.approvals.insert().values(
                    tenant_id=self.tenant,
                    id=uid("appr"),
                    case_id=case["id"],
                    intent_id=intent_id,
                    digest=action["digest"],
                    actor=actor,
                    decision=decision.decision,
                    reason=decision.reason,
                    expires_at=now() + timedelta(minutes=30),
                )
            )
            status = "ready" if decision.decision == "approve" else "rejected"
            db.execute(
                update(tables.intents)
                .where(scope(tables.intents, self.tenant, intent_id))
                .values(status=status)
            )
            if decision.decision == "approve":
                self.change(
                    db,
                    case,
                    "approval.granted",
                    actor,
                    reason=decision.reason,
                    next_action="Create the approved provider draft",
                )
                self.queue(db, case, "commit", {"intent_id": intent_id})
            else:
                self.change(
                    db,
                    case,
                    "case.blocked",
                    actor,
                    reason=decision.reason,
                    next_action="Offer rejected; review the case with the customer",
                )
            return {"status": status, "deduplicated": False}

    def request_operation(self, intent_id: str, kind: str):
        with self.engine.begin() as db:
            initial = self.row(db, tables.intents, intent_id)
            case = self.row(db, tables.cases, initial["case_id"], lock=True)
            action = self.row(db, tables.intents, intent_id, lock=True)
            allowed = {
                "commit": {"ready", "executing", "uncertain", "verified"},
                "reconcile": {"uncertain", "executing", "verified"},
            }
            if kind not in allowed or action["status"] not in allowed[kind]:
                raise Conflict("Operation is not available in this state")
            event_id = self.queue(db, case, kind, {"intent_id": intent_id})
            self.record(
                db, case, f"action.{kind}_requested", "local-operator", {"intent_id": intent_id}
            )
            return {"operation_id": event_id, "status": action["status"]}

    def command(self, case_id: str, command: CaseCommand, kind: str):
        with self.engine.begin() as db:
            case = self.row(db, tables.cases, case_id, lock=True)
            if case["version"] != command.expected_version:
                raise Conflict("Case changed; refresh the page")
            self.change(
                db,
                case,
                kind,
                "local-operator",
                reason=command.reason,
                next_action="Manually handled; provider effects remain independently labelled"
                if kind == "case.manual_completed"
                else "Cancelled",
                completion_kind="manual" if kind == "case.manual_completed" else None,
            )
            db.execute(
                update(tables.intents)
                .where(
                    scope(tables.intents, self.tenant),
                    tables.intents.c.case_id == case_id,
                    tables.intents.c.status.in_(["ready", "awaiting_approval"]),
                )
                .values(status="cancelled")
            )
            db.execute(
                update(tables.approvals)
                .where(
                    scope(tables.approvals, self.tenant),
                    tables.approvals.c.case_id == case_id,
                    tables.approvals.c.consumed_at.is_(None),
                )
                .values(revoked_at=now())
            )
            return json_row(case)

    def block(self, case_id: str, reason: str):
        with self.engine.begin() as db:
            case = self.row(db, tables.cases, case_id, lock=True)
            if case["phase"] not in {"completed", "cancelled", "reconciliation_required"}:
                self.change(db, case, "case.blocked", reason=reason, next_action=reason)

    def retry(self, case_id: str):
        with self.engine.begin() as db:
            case = self.row(db, tables.cases, case_id, lock=True)
            if case["phase"] not in {"new", "blocked"}:
                raise Conflict("Only interrupted triage can be retried")
            existing = db.execute(
                select(tables.intents.c.id).where(
                    scope(tables.intents, self.tenant),
                    tables.intents.c.case_id == case_id,
                    tables.intents.c.source_revision == case["source_revision"],
                )
            ).first()
            if existing:
                raise Conflict("Review the existing action or add fresh source evidence")
            return {
                "operation_id": self.queue(
                    db, case, "triage", {"source_revision": case["source_revision"]}
                )
            }
