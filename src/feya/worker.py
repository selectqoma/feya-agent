import asyncio
import logging

import httpx
from sqlalchemy import select, update
from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker

from feya import db as tables
from feya import work_db
from feya.config import settings
from feya.db import make_engine, scope
from feya.domain import AgentResult
from feya.packs import load_packs
from feya.service import Service
from feya.work import WorkService
from feya.workflows import CaseWorkflow, ConversationWorkflow

QUEUE = "feya-cases-v1"
log = logging.getLogger(__name__)


class Activities:
    def __init__(self, service: Service):
        self.service = service
        self.work = WorkService(service.engine, service.tenant, service)

    @activity.defn(name="process_case_event")
    async def process(self, event_id: str):
        s = self.service
        with s.engine.connect() as db:
            event = s.row(db, tables.outbox, event_id)
        if event["processed"]:
            return
        headers = {"Authorization": "Bearer " + settings.agent_token}
        async with httpx.AsyncClient(timeout=190, headers=headers) as client:
            if event["kind"] == "triage":
                task = s.agent_task(event["case_id"], event["payload"]["source_revision"])
                if task:
                    try:
                        response = await client.post(
                            settings.agent_url + "/run", json=task.model_dump()
                        )
                        response.raise_for_status()
                        s.apply_triage(task, AgentResult.model_validate(response.json()))
                    except Exception:
                        s.block(
                            event["case_id"],
                            "Reasoning unavailable or invalid. Retry analysis or handle the case manually.",
                        )
            elif event["kind"] in {"commit", "reconcile"}:
                intent_id = event["payload"]["intent_id"]
                response = await client.post(
                    f"{settings.gateway_url}/actions/{intent_id}/{event['kind']}",
                    headers={"Authorization": "Bearer " + settings.gateway_token},
                )
                if response.status_code == 409:
                    s.block(
                        event["case_id"],
                        "Execution permission expired or changed; inspect the action before continuing.",
                    )
                else:
                    response.raise_for_status()
                    if response.json().get("status") == "executing":
                        response = await client.post(
                            f"{settings.gateway_url}/actions/{intent_id}/reconcile",
                            headers={"Authorization": "Bearer " + settings.gateway_token},
                        )
                        response.raise_for_status()
                        if response.json().get("status") == "executing":
                            return "pending"
            else:
                raise ValueError("Unknown durable event kind")
        with s.engine.begin() as db:
            db.execute(
                update(tables.outbox)
                .where(scope(tables.outbox, s.tenant, event_id))
                .values(processed=True)
            )


    @activity.defn(name="process_work_event")
    async def process_work(self, event_id: str):
        async def run(task):
            async with httpx.AsyncClient(timeout=100) as client:
                response = await client.post(
                    settings.agent_url + "/conversation/run",
                    headers={"Authorization": "Bearer " + settings.agent_token},
                    json=task.model_dump(),
                )
                response.raise_for_status()
                return response.json()

        return await self.work.process_event(event_id, run)


async def dispatch(service: Service, client: Client, *, once=False):
    while True:
        with service.engine.connect() as db:
            events = [
                dict(r)
                for r in db.execute(
                    select(tables.outbox)
                    .where(
                        scope(tables.outbox, service.tenant), tables.outbox.c.published.is_(False)
                    )
                    .order_by(tables.outbox.c.created_at)
                    .limit(100)
                ).mappings()
            ]
        for event in events:
            await client.start_workflow(
                CaseWorkflow.run,
                args=[event["case_id"], []],
                id=f"{service.tenant}/{event['case_id']}/v1",
                task_queue=QUEUE,
                start_signal="event",
                start_signal_args=[event["id"]],
            )
            with service.engine.begin() as db:
                db.execute(
                    update(tables.outbox)
                    .where(scope(tables.outbox, service.tenant, event["id"]))
                    .values(published=True)
                )
        with service.engine.connect() as db:
            work_events = [dict(r) for r in db.execute(
                select(work_db.events).where(
                    scope(work_db.events, service.tenant), work_db.events.c.published.is_(False)
                ).order_by(work_db.events.c.created_at, work_db.events.c.sequence).limit(100)
            ).mappings()]
        for event in work_events:
            object_id = event["task_id"] or event["conversation_id"]
            await client.start_workflow(
                ConversationWorkflow.run,
                args=[object_id, []],
                id=f"{service.tenant}/work/{object_id}/v1",
                task_queue=QUEUE,
                start_signal="event",
                start_signal_args=[event["id"]],
            )
            with service.engine.begin() as db:
                db.execute(update(work_db.events).where(
                    scope(work_db.events, service.tenant, event["id"])
                ).values(published=True))
        if once:
            return
        await asyncio.sleep(0.5)


async def main():
    if not settings.agent_token or not settings.gateway_token:
        raise RuntimeError("Set FEYA_AGENT_TOKEN and FEYA_GATEWAY_TOKEN before starting workers")
    service = Service(
        make_engine(settings.database_url),
        load_packs(settings.pack_dir, settings.company_file),
        settings.tenant_id,
    )
    for attempt in range(30):
        try:
            client = await Client.connect(settings.temporal_address)
            break
        except Exception:
            if attempt == 29:
                raise
            await asyncio.sleep(2)
    activities = Activities(service)
    async with Worker(
        client, task_queue=QUEUE, workflows=[CaseWorkflow, ConversationWorkflow],
        activities=[activities.process, activities.process_work]
    ):
        while True:
            try:
                await dispatch(service, client)
            except Exception:
                log.warning("Outbox delivery interrupted; committed events will be retried")
                await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
