from datetime import timedelta

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from feya import db as tables
from feya.config import settings
from feya.db import make_engine, scope
from feya.domain import digest, now, uid
from feya.packs import load_packs
from feya.policy import action_digest, evaluate
from feya.service import Conflict, Denied, Service


class ProviderUncertain(Exception):
    pass


class FakeProvider:
    """Simulates non-idempotent remote writes; gateway must never invoke one twice."""

    capabilities = frozenset({"email.draft.create", "accounting.offer.create_draft"})
    idempotency_strategy = "exact_correlation_readback"

    def __init__(self, engine, tenant):
        self.engine, self.tenant = engine, tenant

    def set_fault(self, intent_id: str, mode: str):
        with self.engine.begin() as db:
            db.execute(
                insert(tables.provider_faults)
                .values(tenant_id=self.tenant, id=intent_id, mode=mode)
                .on_conflict_do_update(index_elements=["tenant_id", "id"], set_={"mode": mode})
            )

    def execute(self, action: dict) -> str:
        if action["capability"] not in self.capabilities:
            raise Denied("Fake provider does not expose this capability")
        with self.engine.begin() as db:
            fault = db.execute(
                select(tables.provider_faults.c.mode).where(
                    scope(tables.provider_faults, self.tenant, action["id"])
                )
            ).scalar_one_or_none()
            if fault != "read_failure":
                db.execute(
                    update(tables.provider_faults)
                    .where(scope(tables.provider_faults, self.tenant, action["id"]))
                    .values(mode="none")
                )
        if fault == "timeout_before":
            raise ProviderUncertain("No response from provider")
        payload = dict(action["payload"])
        if fault == "mismatch":
            if "total" in payload:
                payload["total"] = "0.01"
            else:
                payload["body"] += " unexpected provider change"
        provider_ref = uid("remote")
        with self.engine.begin() as db:
            # No upsert: a second attempted write would fail the unique correlation constraint.
            db.execute(
                tables.provider_objects.insert().values(
                    tenant_id=self.tenant,
                    id=provider_ref,
                    operation_key=action["idempotency_key"],
                    capability=action["capability"],
                    payload=payload,
                )
            )
        if fault == "timeout_after":
            raise ProviderUncertain("Provider may have committed before response loss")
        return provider_ref

    def find(self, action: dict) -> dict | None:
        with self.engine.begin() as db:
            fault = db.execute(
                select(tables.provider_faults.c.mode).where(
                    scope(tables.provider_faults, self.tenant, action["id"])
                )
            ).scalar_one_or_none()
            if fault == "read_failure":
                db.execute(
                    update(tables.provider_faults)
                    .where(scope(tables.provider_faults, self.tenant, action["id"]))
                    .values(mode="none")
                )
                failed = True
                row = None
            else:
                failed = False
                row = (
                    db.execute(
                        select(tables.provider_objects).where(
                            scope(tables.provider_objects, self.tenant),
                            tables.provider_objects.c.operation_key == action["idempotency_key"],
                        )
                    )
                    .mappings()
                    .first()
                )
        if failed:
            raise ProviderUncertain("Provider read-back temporarily unavailable")
        return dict(row) if row else None


class Gateway:
    def __init__(self, service: Service, provider: FakeProvider):
        self.s, self.provider = service, provider

    def commit(self, intent_id: str):
        s = self.s
        with s.engine.begin() as db:
            initial = s.row(db, tables.intents, intent_id)
            case = s.row(db, tables.cases, initial["case_id"], lock=True)
            action = s.row(db, tables.intents, intent_id, lock=True)
            if action["status"] in {"verified", "executing", "uncertain"}:
                return {"status": action["status"], "provider_ref": action["provider_ref"]}
            if action["status"] != "ready":
                raise Denied("Action has not been authorized for execution")
            effect, reasons = evaluate(
                case, action, s.sources(db, case["id"]), s.packs[case["pack_id"]]
            )
            if effect == "deny":
                db.execute(
                    update(tables.intents)
                    .where(scope(tables.intents, s.tenant, intent_id))
                    .values(status="denied", policy_effect=effect, policy_reasons=reasons)
                )
                s.change(
                    db,
                    case,
                    "case.blocked",
                    "gateway",
                    reason="; ".join(reasons),
                    next_action="Prepare a fresh proposal",
                )
                return {"status": "denied", "reasons": reasons}
            if effect == "require_approval":
                approval = (
                    db.execute(
                        select(tables.approvals)
                        .where(
                            scope(tables.approvals, s.tenant),
                            tables.approvals.c.intent_id == intent_id,
                        )
                        .with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if (
                    not approval
                    or approval["decision"] != "approve"
                    or approval["revoked_at"]
                    or approval["consumed_at"]
                    or approval["expires_at"] <= now()
                    or approval["digest"] != action_digest(action)
                ):
                    raise Denied("A current, unused approval for this exact action is required")
                db.execute(
                    update(tables.approvals)
                    .where(scope(tables.approvals, s.tenant, approval["id"]))
                    .values(consumed_at=now())
                )
            db.execute(
                tables.attempts.insert().values(
                    tenant_id=s.tenant,
                    id=uid("attempt"),
                    case_id=case["id"],
                    intent_id=intent_id,
                    status="started",
                )
            )
            db.execute(
                update(tables.intents)
                .where(scope(tables.intents, s.tenant, intent_id))
                .values(status="executing")
            )
            s.change(
                db, case, "action.started", "gateway", next_action="Waiting for provider read-back"
            )
        # Persist the attempt before I/O; an interrupted execution is never blindly replayed.
        try:
            self.provider.execute(action)
        except Exception:
            return self.uncertain(
                intent_id, "Provider response uncertain; reconcile before another action"
            )
        return self.verify(action)

    def uncertain(self, intent_id: str, reason: str):
        s = self.s
        with s.engine.begin() as db:
            initial = s.row(db, tables.intents, intent_id)
            case = s.row(db, tables.cases, initial["case_id"], lock=True)
            action = s.row(db, tables.intents, intent_id, lock=True)
            if action["status"] == "verified":
                return {"status": "verified", "provider_ref": action["provider_ref"]}
            db.execute(
                update(tables.intents)
                .where(scope(tables.intents, s.tenant, intent_id))
                .values(status="uncertain")
            )
            db.execute(
                update(tables.attempts)
                .where(scope(tables.attempts, s.tenant), tables.attempts.c.intent_id == intent_id)
                .values(status="uncertain", error=reason)
            )
            s.change(db, case, "action.uncertain", "gateway", reason=reason, next_action=reason)
        return {"status": "uncertain", "reason": reason}

    def verify(self, action: dict):
        try:
            observed = self.provider.find(action)
        except ProviderUncertain:
            return self.uncertain(action["id"], "Read-back unavailable; recheck the provider")
        if observed is None:
            return self.uncertain(
                action["id"], "No matching provider record found; no automatic retry"
            )
        passed = (
            observed["payload"] == action["payload"]
            and observed["capability"] == action["capability"]
        )
        s = self.s
        with s.engine.begin() as db:
            case = s.row(db, tables.cases, action["case_id"], lock=True)
            current = s.row(db, tables.intents, action["id"], lock=True)
            if current["status"] == "verified":
                return {"status": "verified", "provider_ref": current["provider_ref"]}
            db.execute(
                tables.verifications.insert().values(
                    tenant_id=s.tenant,
                    id=uid("verify"),
                    case_id=case["id"],
                    intent_id=action["id"],
                    provider_ref=observed["id"],
                    passed=passed,
                    expected_hash=digest(action["payload"]),
                    observed_hash=digest(observed["payload"]),
                    checked_fields=sorted(action["payload"]),
                )
            )
            db.execute(
                update(tables.intents)
                .where(scope(tables.intents, s.tenant, action["id"]))
                .values(provider_ref=observed["id"])
            )
            s.record(
                db,
                case,
                "action.readback",
                "gateway",
                {"intent_id": action["id"], "passed": passed},
            )
            if passed:
                s.change(db, case, "action.returned", "gateway")
                db.execute(
                    update(tables.intents)
                    .where(scope(tables.intents, s.tenant, action["id"]))
                    .values(status="verified")
                )
                db.execute(
                    update(tables.attempts)
                    .where(
                        scope(tables.attempts, s.tenant),
                        tables.attempts.c.intent_id == action["id"],
                    )
                    .values(status="verified", error=None)
                )
                is_offer = action["capability"] == "accounting.offer.create_draft"
                unresolved = db.execute(
                    select(tables.intents.c.id).where(
                        scope(tables.intents, s.tenant),
                        tables.intents.c.case_id == case["id"],
                        tables.intents.c.status.in_(
                            ["ready", "awaiting_approval", "executing", "uncertain"]
                        ),
                    )
                ).first()
                if is_offer and unresolved:
                    raise Conflict("Other operations remain unresolved")
                s.change(
                    db,
                    case,
                    "case.completed" if is_offer else "draft.verified",
                    "gateway",
                    verified=True,
                    next_action="Provider offer draft verified. Dispatch remains a human task."
                    if is_offer
                    else "Information request saved as a draft. Awaiting customer reply.",
                    completion_kind="verified_draft" if is_offer else None,
                )
                return {"status": "verified", "provider_ref": observed["id"]}
        return self.uncertain(
            action["id"],
            "Provider content differs from the approved draft; operator review required",
        )

    def reconcile(self, intent_id: str):
        with self.s.engine.connect() as db:
            action = self.s.row(db, tables.intents, intent_id)
            if action["status"] == "verified":
                return {"status": "verified", "provider_ref": action["provider_ref"]}
            if action["status"] not in {"uncertain", "executing"}:
                raise Conflict("Only an interrupted operation can be reconciled")
            if action["status"] == "executing":
                attempt = (
                    db.execute(
                        select(tables.attempts).where(
                            scope(tables.attempts, self.s.tenant),
                            tables.attempts.c.intent_id == intent_id,
                        )
                    )
                    .mappings()
                    .one()
                )
                if attempt["created_at"] > now() - timedelta(seconds=30):
                    return {
                        "status": "executing",
                        "reason": "An execution is still in progress; recheck shortly",
                    }
        return self.verify(action)


def service_auth(authorization: str = Header(default="")):
    import secrets

    if not settings.gateway_token or not secrets.compare_digest(
        authorization, "Bearer " + settings.gateway_token
    ):
        raise HTTPException(401, "Service authentication required")


def create_gateway_app():
    app = FastAPI(title="Feya private execution gateway", dependencies=[Depends(service_auth)])
    service = Service(
        make_engine(settings.database_url), load_packs(settings.pack_dir), settings.tenant_id
    )
    gateway = Gateway(service, FakeProvider(service.engine, service.tenant))

    @app.post("/actions/{intent_id}/{operation}")
    def action(intent_id: str, operation: str):
        try:
            if operation == "commit":
                return gateway.commit(intent_id)
            if operation == "reconcile":
                return gateway.reconcile(intent_id)
            raise HTTPException(404, "Unknown gateway operation")
        except (Denied, Conflict) as exc:
            raise HTTPException(409, str(exc)) from exc

    return app
