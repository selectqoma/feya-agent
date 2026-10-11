from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from feya.domain import EmailDraft, OfferDraft, digest
from feya.packs import BusinessPack

POLICY_VERSION = "safe-drafts:1"


def action_digest(action: dict) -> str:
    return digest(
        {
            k: action[k]
            for k in (
                "tenant_id",
                "id",
                "case_id",
                "capability",
                "payload",
                "evidence_ids",
                "source_revision",
                "pack_hash",
                "idempotency_key",
            )
        }
        | {"policy_version": POLICY_VERSION}
    )


def evaluate(
    case: dict, action: dict, sources: list[dict], pack: BusinessPack
) -> tuple[str, list[str]]:
    reasons = []
    if action["tenant_id"] != case["tenant_id"] or action["case_id"] != case["id"]:
        reasons.append("Case and action scope differ")
    if case["phase"] in {"cancelled", "completed", "blocked"}:
        reasons.append("Case is not open for execution")
    if action["source_revision"] != case["source_revision"]:
        reasons.append("Evidence changed; prepare a fresh proposal")
    if action["pack_hash"] != pack.fingerprint or case["pack_hash"] != pack.fingerprint:
        reasons.append("Business pack changed; prepare a fresh case decision")
    if action["digest"] != action_digest(action):
        reasons.append("Action contents do not match their trusted digest")
    indexed = {s["id"]: s for s in sources}
    if not action["evidence_ids"] or set(action["evidence_ids"]) != set(indexed):
        reasons.append("All current source evidence must be included")
    for source in sources:
        if source["tenant_id"] != case["tenant_id"] or source["case_id"] != case["id"]:
            reasons.append("Evidence is outside this case")
        if digest(source["content"]) != source["content_hash"]:
            reasons.append("Evidence integrity check failed")
        observed = source["created_at"]
        if isinstance(observed, str):
            observed = datetime.fromisoformat(observed)
        if observed < datetime.now(UTC) - timedelta(days=7):
            reasons.append("Source snapshot is stale; refresh before execution")
    try:
        if action["capability"] == "email.draft.create":
            payload = EmailDraft.model_validate(action["payload"])
            if payload.to != case["customer_email"]:
                reasons.append("Recipient must exactly match the verified source sender")
            if "\r" in payload.to + payload.subject or "\n" in payload.to + payload.subject:
                reasons.append("Invalid email headers")
            effect = "allow"
        elif action["capability"] == "accounting.offer.create_draft":
            OfferDraft.model_validate(action["payload"])
            if case["missing"]:
                reasons.append("Required business facts are missing")
            facts = {k: v["value"] for k, v in case["facts"].items()}
            for fact in case["facts"].values():
                fact_source = indexed.get(fact["evidence_id"])
                if (
                    fact_source is None
                    or fact["quote"] not in fact_source["content"]["body"]
                    or fact["value"] not in fact["quote"]
                ):
                    reasons.append("A business fact has no matching source evidence")
            expected = pack.quote(facts, case["customer_email"])
            if action["payload"] != expected:
                reasons.append("Offer does not match the approved rate calculation and customer")
            effect = "require_approval"
        else:
            reasons.append("Capability is not permitted by the system safety floor")
            effect = "deny"
    except (ValidationError, ValueError, KeyError):
        reasons.append("Payload or pricing inputs are invalid")
        effect = "deny"
    return (
        ("deny", sorted(set(reasons)))
        if reasons
        else (
            effect,
            [
                "Source identity and evidence verified",
                "Draft only; dispatch is disabled",
                *(
                    ["Deterministic price validated; exact human approval required"]
                    if effect == "require_approval"
                    else []
                ),
            ],
        )
    )
