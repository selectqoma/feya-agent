"""Exercise the actual local UI and capture desktop/mobile evidence."""

import asyncio
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8010"


async def wait_phase(client, case_id, phase):
    for _ in range(90):
        case = (await client.get(f"{BASE}/v1/cases/{case_id}")).json()
        if case["phase"] == phase:
            return case
        await asyncio.sleep(1)
    raise AssertionError(f"Case did not reach {phase}: {case['phase']}")


async def main():
    async with httpx.AsyncClient(headers={"X-Feya-Local": "1"}) as client:
        result = await client.post(BASE + "/v1/demo/consulting", json={})
        result.raise_for_status()
        case_id = result.json()["case_id"]
        await wait_phase(client, case_id, "waiting_for_information")
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(BASE)
            await page.get_by_role("heading", name="A little clarity for your day.").wait_for()
            await page.get_by_role(
                "button", name="A clearer customer onboarding process sam@example.test"
            ).first.click()
            await page.get_by_role("button", name="Simulate the customer’s reply").click()
            await wait_phase(client, case_id, "awaiting_review")
            await page.get_by_role("button", name="Approve draft").wait_for(timeout=12000)
            await page.get_by_text("Try a simulated provider failure").click()
            await page.get_by_label("Provider failure simulation").select_option("timeout_after")
            await page.get_by_role("button", name="Approve draft").click()
            await wait_phase(client, case_id, "reconciliation_required")
            await page.get_by_role("button", name="Recheck provider").wait_for(timeout=12000)
            await page.screenshot(path=".local/verification-needed.png", full_page=True)
            await page.get_by_role("button", name="Recheck provider").click()
            case = await wait_phase(client, case_id, "completed")
            assert (
                len(
                    [
                        a
                        for a in case["actions"]
                        if a["capability"] == "accounting.offer.create_draft"
                    ]
                )
                == 1
            )
            await page.get_by_text("Provider draft verified", exact=False).wait_for(timeout=12000)
            await page.get_by_role("button", name="Sources", exact=False).click()
            await page.get_by_text("Immutable observation · simulated email").first.wait_for()
            await page.keyboard.press("Escape")
            await page.screenshot(path=".local/workspace-desktop.png", full_page=True)
            await page.get_by_role("button", name="Business packs", exact=True).click()
            await page.get_by_role("heading", name="Consulting proposals").wait_for()
            await page.get_by_role("button", name="Today", exact=True).click()
            await page.get_by_role("button", name="New enquiry", exact=True).click()
            await page.get_by_role("button", name="Use the example message").click()
            await page.get_by_role("button", name="Create case", exact=True).click()
            await page.get_by_role("dialog", name="Case detail").wait_for()
            await page.keyboard.press("Escape")
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.screenshot(path=".local/workspace-mobile.png", full_page=True)
            assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert errors == [], errors
            await browser.close()
            print(
                "Browser journey passed: enquiry, reply, approval, lost response, reconciliation, sources, creation, responsive layout. No JS errors."
            )


if __name__ == "__main__":
    Path(".local").mkdir(exist_ok=True)
    asyncio.run(main())
