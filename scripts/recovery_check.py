"""Kill only this checkout's local worker while an approval is waiting, then replay."""

import asyncio
import os
import signal
import subprocess
import sys

import httpx
from sqlalchemy import select, update

from feya import db as t
from feya.cli import ROOT, load_environment
from feya.db import make_engine, scope


async def phase(client, case_id, wanted):
    for _ in range(90):
        case = (await client.get(f"/v1/cases/{case_id}")).json()
        if case["phase"] == wanted:
            return case
        await asyncio.sleep(1)
    raise AssertionError(f"Wanted {wanted}; got {case['phase']}")


async def main():
    load_environment()
    from feya.config import settings

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8010", headers={"X-Feya-Local": "1"}
    ) as client:
        response = await client.post("/v1/demo/generic_enquiry", json={})
        response.raise_for_status()
        case_id = response.json()["case_id"]
        await phase(client, case_id, "waiting_for_information")
        await client.post(f"/v1/cases/{case_id}/demo-reply", json={})
        case = await phase(client, case_id, "awaiting_review")
        pidfile = ROOT / ".local/worker.pid"
        pid = int(pidfile.read_text())
        cmd = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=True
        ).stdout
        cwd = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert str(ROOT) in cwd and "feya.worker" in cmd, "Refusing to stop an unrelated process"
        os.kill(pid, signal.SIGKILL)
        pidfile.unlink()
        action = case["actions"][-1]
        decision = await client.post(
            f"/v1/approvals/{action['id']}/decide",
            json={
                "decision": "approve",
                "expected_digest": action["digest"],
                "reason": "Synthetic crash-recovery exercise",
            },
        )
        decision.raise_for_status()
        await asyncio.sleep(1)
        assert (await client.get(f"/v1/cases/{case_id}")).json()["phase"] == "ready_to_execute"
        subprocess.run(
            [sys.executable, "-c", "from feya.cli import up; up(True)"], cwd=ROOT, check=True
        )
        await phase(client, case_id, "completed")
        engine = make_engine(settings.database_url)
        with engine.begin() as db:
            db.execute(
                update(t.outbox)
                .where(scope(t.outbox, settings.tenant_id), t.outbox.c.case_id == case_id)
                .values(published=False)
            )
        await asyncio.sleep(2)
        with engine.connect() as db:
            objects = (
                db.execute(
                    select(t.provider_objects).where(
                        scope(t.provider_objects, settings.tenant_id),
                        t.provider_objects.c.operation_key.like(case_id + ":%"),
                    )
                )
                .mappings()
                .all()
            )
        assert len(objects) == 2, "Exactly one reply draft and one offer draft expected"
        assert sum(o["capability"] == "accounting.offer.create_draft" for o in objects) == 1
        engine.dispose()
        print(
            "Recovery passed: SIGKILL while waiting, approval persisted without worker, restart, outbox redelivery, one verified offer."
        )


if __name__ == "__main__":
    asyncio.run(main())
