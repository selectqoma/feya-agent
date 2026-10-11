from fastapi.testclient import TestClient

from feya.api import create_app
from feya.conversation_agent import ConversationFixtureRunner
from feya.domain import uid


async def test_conversation_api_delegation_download_and_boundaries(service):
    app = create_app(service=service)
    client = TestClient(app)
    path = "/v1/conversations"
    assert client.post(path, json={"title": "Planning"}).status_code == 403
    client.headers["X-Feya-Local"] = "1"
    assert client.post(path, json={"title": "Planning", "tenant_id": "other"}).status_code == 422
    assert client.post(path, json={"title": " "}).status_code == 422
    created = client.post(path, json={"title": "Planning"})
    assert created.status_code == 201
    conversation = created.json()["id"]
    path += "/" + conversation
    assert client.post(path + "/sources", json={"title": "Notes", "content": "A costs 10; B costs 20."}).status_code == 201
    body = {"content": "Compare the suppliers from my notes", "request_id": uid("request")}
    queued = client.post(path + "/messages", json=body)
    assert queued.status_code == 202
    repeated = client.post(path + "/messages", json=body).json()
    assert repeated["deduplicated"] and repeated["event_id"] == queued.json()["event_id"]
    assert client.post(path + "/messages", json=body | {"content": "changed"}).status_code == 409
    await app.state.work.process_event(queued.json()["event_id"], ConversationFixtureRunner().run)
    task = client.get(path).json()["tasks"][0]
    assert task["status"] == "queued"
    assert client.get(f"/v1/tasks/{task['id']}/artifact").status_code != 200
    from sqlalchemy import select

    from feya import work_db
    from feya.db import scope

    with service.engine.connect() as db:
        event_id = db.execute(select(work_db.events.c.id).where(
            scope(work_db.events, service.tenant), work_db.events.c.task_id == task["id"]
        )).scalar_one()
    await app.state.work.process_event(event_id, ConversationFixtureRunner().run)
    artifact = client.get(f"/v1/tasks/{task['id']}/artifact")
    assert artifact.status_code == 200
    assert artifact.headers["content-type"].startswith("text/markdown")
    assert "attachment;" in artifact.headers["content-disposition"]
    assert "Offline fixture report" in artifact.text
    assert client.post(f"/v1/tasks/{task['id']}/send", json={"expected_version": 1}).status_code == 404
    assert client.get("/v1/conversations/unknown").status_code == 404
    assert client.get("/v1/tasks/unknown/artifact").status_code == 404
