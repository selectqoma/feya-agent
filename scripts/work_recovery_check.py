"""Exercise a persisted task through worker interruption and duplicate event delivery."""

import asyncio
import os
import signal
import subprocess
import sys

import httpx
from sqlalchemy import select, update

from feya.cli import ROOT, load_environment
from feya.db import make_engine, scope
from feya.domain import uid


async def wait_task(client, conversation_id, status):
    for _ in range(120):
        response = await client.get(f"/v1/conversations/{conversation_id}")
        response.raise_for_status()
        tasks = response.json()["tasks"]
        if tasks and tasks[0]["status"] == status:
            return tasks[0]
        await asyncio.sleep(0.5)
    raise AssertionError(f"Task did not reach {status}: {tasks}")


async def main():
    load_environment()
    from feya import work_db as t
    from feya.config import settings

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8010", headers={"X-Feya-Local": "1"}, timeout=15,
    ) as client:
        workspace = (await client.get("/v1/workspace")).json()
        assert workspace["runner"] == "fixture", "Run with FEYA_RUNNER=fixture for deterministic recovery checks"
        response = await client.post("/v1/conversations", json={"title": "Synthetic recovery check"})
        response.raise_for_status()
        conversation_id = response.json()["id"]
        path = f"/v1/conversations/{conversation_id}"
        message = {"content": "Compare the supplier proposals", "request_id": uid("request")}
        response = await client.post(path + "/messages", json=message)
        response.raise_for_status()
        task = await wait_task(client, conversation_id, "waiting_for_input")
        pidfile = ROOT / ".local/worker.pid"
        pid = int(pidfile.read_text())
        command = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=True,
        ).stdout
        cwd = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True, text=True, check=True,
        ).stdout
        assert str(ROOT) in cwd and "feya.worker" in command, "Refusing to stop an unrelated process"
        os.kill(pid, signal.SIGKILL)
        pidfile.unlink()
        try:
            response = await client.post(path + "/sources", json={
                "title": "Synthetic quotes", "content": "Supplier A: EUR 100, 5 days. Supplier B: EUR 140, 2 days.",
            })
            response.raise_for_status()
            response = await client.post(f"/v1/tasks/{task['id']}/resume", json={
                "expected_version": task["version"], "instruction": "Compare the provided quotes.",
            })
            response.raise_for_status()
            assert response.json()["status"] == "queued"
            repeated = await client.post(path + "/messages", json=message)
            assert repeated.json()["deduplicated"]
            await asyncio.sleep(1)
            assert (await client.get(f"/v1/tasks/{task['id']}")).json()["status"] == "queued"
        finally:
            subprocess.run([sys.executable, "-m", "feya.cli", "up", "--skip-infra"], cwd=ROOT, check=True)
        await wait_task(client, conversation_id, "completed")
        engine = make_engine(settings.database_url)
        with engine.begin() as db:
            db.execute(update(t.events).where(
                scope(t.events, settings.tenant_id), t.events.c.conversation_id == conversation_id,
            ).values(published=False))
        await asyncio.sleep(3)
        with engine.connect() as db:
            tasks = db.execute(select(t.tasks).where(
                scope(t.tasks, settings.tenant_id), t.tasks.c.conversation_id == conversation_id,
            )).mappings().all()
            completed = db.execute(select(t.progress).where(
                scope(t.progress, settings.tenant_id), t.progress.c.task_id == task["id"],
                t.progress.c.kind == "completed",
            )).mappings().all()
        engine.dispose()
        assert len(tasks) == len(completed) == 1, "Replay must not duplicate work or results"
        artifact = await client.get(f"/v1/tasks/{task['id']}/artifact")
        assert artifact.status_code == 200 and "Synthetic quotes" in artifact.text
        print("Task recovery passed: wait for input, kill worker, persist source/resume, restart, replay; one task and saved result.")


if __name__ == "__main__":
    asyncio.run(main())
