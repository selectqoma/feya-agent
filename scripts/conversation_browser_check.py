"""Exercise browser conversation controls against deterministic API route fixtures."""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8010"


async def main():
    conversation = {
        "id": "conversation_browser",
        "title": "Supplier comparison",
        "messages": [],
        "sources": [],
        "tasks": [],
        "pending": 0,
    }
    task = {
        "id": "task_browser",
        "objective": "Compare the two supplied proposals",
        "deliverable": "A comparison with a recommendation",
        "status": "running",
        "version": 1,
        "progress": [{"id": "progress_browser", "kind": "working", "content": "Reviewing supplier proposals.", "created_at": "2026-10-11T12:00:02Z"}],
        "result_markdown": "",
    }
    requests = []

    async def route_api(route):
        request = route.request
        path = request.url.split("/v1", 1)[1]
        data = request.post_data_json if request.method == "POST" else None
        if data is not None:
            assert request.headers["x-feya-local"] == "1"
            requests.append((path, data))
        value = {}
        if path == "/workspace":
            value = {
                "name": "Example company", "runner": "fixture", "model": "fixture",
                "temporal": "connected", "backlog": 0, "packs": [],
            }
        elif path == "/cases":
            value = []
        elif path == "/conversations":
            value = [conversation] if requests else []
            if data:
                conversation["title"] = data["title"]
                value = conversation
        elif path == "/conversations/conversation_browser":
            value = conversation
        elif path.endswith("/sources"):
            conversation["sources"].append({"id": "source_browser", **data})
        elif path.endswith("/messages"):
            number = len(conversation["messages"])
            conversation["messages"].extend([
                {"id": f"message_{number}", "role": "user", "content": data["content"],
                 "created_at": "2026-10-11T12:00:00Z"},
                {"id": f"message_{number + 1}", "role": "assistant",
                 "content": "I will compare the supplied proposals. You can keep chatting.",
                 "task_id": task["id"], "created_at": "2026-10-11T12:00:01Z"},
            ])
            conversation["tasks"] = [task]
        elif path == "/tasks/task_browser":
            value = {**task, "sources": conversation["sources"], "events": []}
        elif path.startswith("/tasks/task_browser/"):
            assert data["expected_version"] == task["version"]
            if path.endswith("/resume"):
                assert task["status"] in ["waiting_for_input", "failed"]
            task["version"] += 1
            task["status"] = "cancelled" if path.endswith("/cancel") else "running"
            value = task
        else:
            raise AssertionError(f"Unexpected request: {path}")
        await route.fulfill(content_type="application/json", body=json.dumps(value))

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 1050})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.route("**/v1/**", route_api)
        await page.goto(BASE)
        await page.get_by_role("heading", name="What shall we work on?").wait_for()
        await page.get_by_role("button", name="Add source", exact=True).click()
        await page.get_by_label("Source title").fill("Supplier proposals")
        await page.get_by_label("Paste notes or document text").fill(
            "Supplier A: €100, delivery Monday. Supplier B: €120, delivery Friday."
        )
        await page.locator(".conversation-source-form").get_by_role("button", name="Add source", exact=True).click()
        await page.get_by_text("Supplier proposals", exact=True).last.wait_for()
        await page.get_by_label("Message Feya").fill("Compare these suppliers and recommend one.")
        await page.get_by_role("button", name="Send", exact=True).click()
        await page.get_by_role("button", name="View task").click()
        await page.get_by_label("Additional instructions").fill("Prioritize delivery date.")
        await page.get_by_role("button", name="Update task", exact=True).click()
        assert requests[-1][1]["instruction"] == "Prioritize delivery date."
        await page.get_by_label("Message Feya").fill("Explain the criteria while you work.")
        await page.get_by_role("button", name="Send", exact=True).click()
        await page.get_by_text("Explain the criteria while you work.", exact=True).wait_for()
        for status in ["waiting_for_input", "failed"]:
            task["status"] = status
            await page.get_by_role("button", name="Resume", exact=True).wait_for(timeout=10000)
            await page.get_by_role("button", name="Resume", exact=True).click()
            assert task["status"] == "running"
        await page.screenshot(path=".local/conversation-desktop.png", full_page=True)
        task["status"] = "completed"
        task["result_markdown"] = "Choose Supplier A: lower price and earlier delivery."
        await page.get_by_role("link", name="Download result").wait_for(timeout=10000)
        await page.get_by_text("Read result", exact=True).click()
        await page.get_by_text(task["result_markdown"], exact=True).wait_for()
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.get_by_text("Explain the criteria while you work.", exact=True).wait_for()
        await page.screenshot(path=".local/conversation-mobile.png", full_page=True)
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        task["status"] = "running"
        await page.get_by_role("button", name="Cancel task", exact=True).wait_for(timeout=10000)
        await page.get_by_role("button", name="Cancel task", exact=True).click()
        await page.get_by_text("This task was cancelled.", exact=False).wait_for()
        assert await page.get_by_role("button", name="Resume", exact=True).count() == 0
        assert await page.get_by_label("Additional instructions").count() == 0
        assert errors == [], errors
        await browser.close()
    print("Conversation browser checks passed: source, delegation, concurrent chat, steer, cancel, resume, result, responsive layout.")


if __name__ == "__main__":
    Path(".local").mkdir(exist_ok=True)
    asyncio.run(main())
