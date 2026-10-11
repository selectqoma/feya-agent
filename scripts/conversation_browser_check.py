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
        "acceptance_criteria": ["Compare prices and delivery dates", "Make a recommendation"],
        "calls_reserved": 2, "tokens_reserved": 16000, "seconds_reserved": 180,
        "unknown_usage_calls": 1,
        "limits": {"calls": 12, "tokens": 420000, "active_seconds": 1080, "generation_calls": 4},
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
        external_requests = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: external_requests.append(request.url) if request.url.startswith("https://untrusted.invalid") else None)
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
        await page.get_by_text("Acceptance criteria", exact=True).wait_for(timeout=10000)
        await page.get_by_text("Compare prices and delivery dates", exact=True).wait_for()
        await page.get_by_text("Work budget · 2/12 requests", exact=True).click()
        await page.get_by_text("1 calls have unconfirmed usage.", exact=False).wait_for()
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
        task.update(status="failed", can_resume=False, error_code="budget_exhausted",
                    candidate_markdown="## Candidate preview\n\nA **saved** draft.",
                    failure_message="The work budget is exhausted.")
        await page.get_by_text("The work budget is exhausted.", exact=True).wait_for(timeout=10000)
        assert await page.get_by_role("button", name="Resume", exact=True).is_disabled()
        await page.get_by_text("Read unapproved draft", exact=True).click()
        await page.get_by_role("heading", name="Candidate preview", level=2).wait_for()
        await page.screenshot(path=".local/conversation-desktop.png", full_page=True)
        task["status"] = "completed"
        task.update(failure_message="", completion_label="draft_prepared", completion_checks={
            "passed": True, "label": "draft_prepared", "checks": [
                {"name": "criteria_coverage", "passed": True, "detail": "All criteria assessed."},
                {"name": "citation_evidence", "passed": False, "blocking": False, "detail": "Source support assessed by the agent; excerpts did not match exactly."},
            ],
        })
        task["result_markdown"] = (
            "## Internal Payment-Terms Summary\n\n"
            "- **Payment deadline:** Payment is due within 30 days. [source_browser]\n"
            "- *Human review* before sending.\n\n"
            "| Supplier | Price |\n| --- | --- |\n| A | EUR 100 |\n\n"
            "Literal code: `[source_browser]`\n\n"
            "```text\n**not bold** [source_browser]\n```\n\n"
            "Unknown source [source_missing].\n\n"
            "[Unsafe](javascript:alert(1)) [Local](/v1/workspace) [Example](https://example.com)\n\n"
            '<img src="https://untrusted.invalid/html" onerror="alert(1)">\n\n'
            "![Remote image](https://untrusted.invalid/markdown)"
        )
        conversation["messages"].append({"id": "formatted_answer", "role": "assistant",
            "content": task["result_markdown"], "created_at": "2026-10-11T12:02:00Z"})
        await page.get_by_role("link", name="Download result").wait_for(timeout=10000)
        await page.get_by_text("Draft prepared", exact=True).wait_for()
        await page.get_by_text("Draft review complete", exact=True).click()
        await page.get_by_text("Review note · Citation evidence", exact=True).wait_for()
        await page.get_by_text("Source support assessed by the agent; excerpts did not match exactly.", exact=True).wait_for()
        await page.get_by_text("Read result", exact=True).click()
        report = page.locator(".conversation-task-detail .markdown-content").last
        await report.get_by_role("heading", name="Internal Payment-Terms Summary", level=2).wait_for()
        assert await report.locator("strong").inner_text() == "Payment deadline:"
        assert await report.locator("table tbody td").all_text_contents() == ["A", "EUR 100"]
        assert "**not bold** [source_browser]" in await report.locator("pre code").inner_text()
        assert await report.locator("code .source-citation").count() == 0
        assert await report.get_by_role("link", name="Unsafe", exact=True).count() == 0
        assert await report.get_by_role("link", name="Local", exact=True).count() == 0
        assert await report.locator("img, script, iframe").count() == 0
        assert "source_missing" in await report.inner_text()
        assert await report.get_by_role("link", name="Example", exact=True).get_attribute("rel") == "noopener noreferrer"
        citation = report.get_by_role("link", name="Supplier proposals", exact=True)
        await citation.click()
        assert await page.locator("#source-source_browser").get_attribute("open") is not None
        assert await page.locator("#source-source_browser summary").evaluate("el => el === document.activeElement")
        await page.locator(".role-assistant").last.get_by_role("heading", name="Internal Payment-Terms Summary").wait_for()
        assert external_requests == []
        await page.screenshot(path=".local/markdown-desktop.png", full_page=True)
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.get_by_text("Explain the criteria while you work.", exact=True).wait_for()
        await page.screenshot(path=".local/conversation-mobile.png", full_page=True)
        await page.screenshot(path=".local/markdown-mobile.png", full_page=True)
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
