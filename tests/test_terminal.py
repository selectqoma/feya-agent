import json
import os
from pathlib import Path

import httpx
import pytest

from feya import terminal
from feya.onboarding import save_company, setup
from feya.packs import BusinessPack, load_company, load_packs


def answers(monkeypatch, values):
    iterator = iter(values)
    monkeypatch.setattr("builtins.input", lambda _: next(iterator))


def test_setup_creates_private_usable_pack_and_preserves_safety(tmp_path, monkeypatch):
    path = tmp_path / ".local/company.yaml"
    answers(monkeypatch, ["consulting", "Example Studio", "USD", "0.10", "100.00", "200.00", "y"])
    setup(tmp_path, path, Path("packs"))
    company = load_company(path)
    assert company is not None
    assert company.name == "Example Studio"
    assert company.version == "0.1.0"
    assert path.stat().st_mode & 0o777 == 0o600
    assert company.require_offer_approval and company.default_outbound_dispatch == "deny"
    assert (
        company.quote({"service": "discovery", "quantity": "2"}, "a@example.test")["total"]
        == "220.00"
    )
    assert company.id in load_packs(Path("packs"), path)
    assert len(load_packs(Path("packs"), path)) == 3
    assert "example.test" in company.fixture["sender"]
    assert not (tmp_path / ".env").exists()

    answers(monkeypatch, ["Example Studio", "", "", "150.00", "", "y"])
    setup(tmp_path, path, Path("packs"))
    changed = load_company(path)
    assert changed.id == company.id
    assert changed.version == "0.1.1"
    assert changed.fingerprint != company.fingerprint


def test_setup_cancel_and_eof_leave_previous_file_intact(tmp_path, monkeypatch):
    path = tmp_path / "company.yaml"
    pack = load_packs(Path("packs"))["consulting"]
    save_company(path, pack, None)
    before = path.read_bytes()
    answers(monkeypatch, ["Other Company", "", "", "", "", "n"])
    setup(tmp_path, path, Path("packs"))
    assert path.read_bytes() == before

    answers(monkeypatch, ["", "", "", "", ""])
    setup(tmp_path, path, Path("packs"))
    assert path.read_bytes() == before

    def eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    with pytest.raises(EOFError):
        setup(tmp_path, path, Path("packs"))
    assert path.read_bytes() == before


def test_setup_reprompts_invalid_financial_values(tmp_path, monkeypatch, capsys):
    path = tmp_path / "company.yaml"
    answers(
        monkeypatch,
        ["consulting", "Test", "CAD", "EUR", "21", "0.21", "NaN", "-1.00", "10.00", "20.00", "y"],
    )
    setup(tmp_path, path, Path("packs"))
    assert load_company(path).rates["discovery"].unit_price == "10.00"
    assert capsys.readouterr().out.count("Please enter a valid value") == 4


def test_setup_refuses_running_services_and_stale_edits(tmp_path, monkeypatch):
    path = tmp_path / ".local/company.yaml"
    path.parent.mkdir()
    pid = path.parent / "api.pid"
    pid.write_text(str(os.getpid()))
    with pytest.raises(ValueError, match="Stop the local app"):
        setup(tmp_path, path, Path("packs"))
    assert not path.exists()
    pid.unlink()
    pack = load_packs(Path("packs"))["consulting"]
    save_company(path, pack, None)
    with pytest.raises(ValueError, match="changed while"):
        save_company(path, pack, None)
    assert load_company(path) == pack


def install_api(monkeypatch, *, company=None, tenant="tenant_demo", status=202):
    writes = []
    action = {
        "id": "action_1",
        "status": "awaiting_approval",
        "digest": "a" * 64,
        "payload": {"total": "220.00", "customer_email": "a@example.test"},
    }
    workspace = {
        "tenant_id": tenant,
        "company_pack_id": company.id if company else None,
        "packs": [{"id": company.id, "fingerprint": company.fingerprint}] if company else [],
    }

    def respond(request):
        if request.method == "POST":
            writes.append((request.url.path, json.loads(request.content)))
            return httpx.Response(status, json={"status": "recorded"})
        if request.url.path == "/v1/workspace":
            return httpx.Response(200, json=workspace)
        return httpx.Response(
            200,
            json={
                "id": "case_1",
                "subject": "Example\x1b[2J",
                "facts": {},
                "evidence": [],
                "actions": [action],
            },
        )

    client = httpx.Client
    monkeypatch.setattr(
        terminal.httpx,
        "Client",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )
    return writes, action


def test_terminal_approval_uses_reviewed_digest_and_escapes_sources(tmp_path, monkeypatch, capsys):
    writes, action = install_api(monkeypatch)
    answers(monkeypatch, ["approve", "Checked exact recipient and price"])
    terminal.operate("approve", "case_1", tmp_path / "company.yaml", "tenant_demo")
    assert writes == [
        (
            "/v1/approvals/action_1/decide",
            {
                "decision": "approve",
                "expected_digest": action["digest"],
                "reason": "Checked exact recipient and price",
            },
        )
    ]
    output = capsys.readouterr().out
    assert "220.00" in output and "a@example.test" in output
    assert "\x1b" not in output and r"\u001b" in output


def test_terminal_cancel_never_posts(tmp_path, monkeypatch):
    writes, _ = install_api(monkeypatch)
    answers(monkeypatch, [""])
    terminal.operate("approve", "case_1", tmp_path / "company.yaml", "tenant_demo")
    assert writes == []


def test_terminal_stale_approval_is_not_retried(tmp_path, monkeypatch):
    writes, _ = install_api(monkeypatch, status=409)
    answers(monkeypatch, ["approve", "Reviewed"])
    with pytest.raises(httpx.HTTPStatusError):
        terminal.operate("approve", "case_1", tmp_path / "company.yaml", "tenant_demo")
    assert len(writes) == 1


def test_terminal_rejects_wrong_company_or_tenant(tmp_path, monkeypatch):
    path = tmp_path / "company.yaml"
    company = load_packs(Path("packs"))["consulting"]
    save_company(path, company, None)
    writes, _ = install_api(monkeypatch)
    with pytest.raises(ValueError, match="stale"):
        terminal.operate("demo", None, path, "tenant_demo")
    with pytest.raises(ValueError, match="differs"):
        terminal.operate("demo", None, path, "another_tenant")
    assert writes == []


def test_demo_defaults_to_company_pack(tmp_path, monkeypatch):
    path = tmp_path / "company.yaml"
    company = load_packs(Path("packs"))["consulting"]
    save_company(path, company, None)
    writes, _ = install_api(monkeypatch, company=company)
    terminal.operate("demo", None, path, "tenant_demo")
    assert writes == [("/v1/demo/consulting", {})]


def test_company_pack_cannot_shadow_builtin(tmp_path):
    path = tmp_path / "company.yaml"
    save_company(path, load_packs(Path("packs"))["consulting"], None)
    with pytest.raises(ValueError, match="duplicated"):
        load_packs(Path("packs"), path)


async def test_company_case_uses_custom_rates_and_gateway(service, gateway, tmp_path):
    from conftest import enquiry

    from feya.agents import FixtureRunner
    from feya.domain import Decision

    template = service.packs["consulting"].model_dump()
    template["rates"]["discovery"]["unit_price"] = "100.00"
    company = BusinessPack.model_validate(
        template | {"id": "company_test", "name": "Test Company", "tax_rate": "0.10"}
    )
    path = tmp_path / "company.yaml"
    save_company(path, company, None)
    service.packs = load_packs(Path("packs"), path)
    event = enquiry("consulting", complete=True).model_copy(update={"pack_id": company.id})
    case_id = service.ingest(event)["case_id"]
    task = service.agent_task(case_id, 1)
    service.apply_triage(task, await FixtureRunner().run(task))
    action = service.detail(case_id)["actions"][-1]
    assert action["payload"]["total"] == "220.00"
    service.decide(
        action["id"],
        Decision(decision="approve", expected_digest=action["digest"], reason="Reviewed"),
    )
    gateway.commit(action["id"])
    assert service.detail(case_id)["phase"] == "completed"


def install_conversation_api(monkeypatch, *, lost_response=False, pending=0, failed_poll=False):
    calls = []
    messages = []
    failed_once = False

    def respond(request):
        nonlocal failed_once
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        calls.append((request.method, path, body))
        if path == "/v1/workspace":
            return httpx.Response(200, json={"tenant_id": "tenant_demo", "packs": []})
        if path == "/v1/conversations" and request.method == "POST":
            return httpx.Response(201, json={"id": "conv_1", "title": body["title"]})
        if path.endswith("/messages"):
            if not messages:
                messages.extend([
                    {"id": "msg_1", "role": "user", "content": body["content"], "sequence": 1},
                    {"id": "msg_2", "role": "assistant", "content": "Hello\x1b[2J", "sequence": 2},
                ])
            if lost_response and not failed_once:
                failed_once = True
                raise httpx.ReadTimeout("lost response", request=request)
            return httpx.Response(202, json={"message_id": "msg_1", "deduplicated": failed_once})
        if path == "/v1/conversations/conv_1":
            if failed_poll:
                raise httpx.ReadTimeout("poll unavailable", request=request)
            return httpx.Response(200, json={"id": "conv_1", "messages": messages, "pending": pending})
        if path == "/v1/tasks/task_1" and request.method == "GET":
            return httpx.Response(200, json={"id": "task_1", "version": 3, "status": "running"})
        return httpx.Response(200, json={"status": "accepted"})

    client = httpx.Client
    monkeypatch.setattr(terminal.httpx, "Client", lambda **kwargs: client(
        transport=httpx.MockTransport(respond), **kwargs
    ))
    return calls


def test_shell_only_slash_commands_can_execute(monkeypatch, tmp_path):
    calls = []
    answers(monkeypatch, ["down", "write 'a draft", "/cases", "/exit"])
    monkeypatch.setattr(terminal.subprocess, "run", lambda args, **kwargs: calls.append(args))
    terminal.shell(tmp_path)
    assert calls[0][-3:] == ["ask", "--", "down"]
    assert calls[1][-3:] == ["ask", "--", "write 'a draft"]
    assert calls[2][-1] == "cases"


def test_conversation_selection_is_private_and_reused(tmp_path, monkeypatch, capsys):
    calls = install_conversation_api(monkeypatch)
    company_file = tmp_path / "company.yaml"
    terminal.converse("ask", None, "Hello", tmp_path, company_file, "tenant_demo")
    state = next((tmp_path / ".local").glob("conversation-*.json"))
    assert state.stat().st_mode & 0o777 == 0o600
    assert json.loads(state.read_text()) == {"conversation_id": "conv_1"}
    terminal.converse("messages", None, "", tmp_path, company_file, "tenant_demo")
    assert len([item for item in calls if item[:2] == ("POST", "/v1/conversations")]) == 1
    output = capsys.readouterr().out
    assert "Hello" in output and "\x1b" not in output and r"\u001b" in output


def test_chat_lost_response_reuses_request_id_and_blocks_changed_retry(tmp_path, monkeypatch):
    calls = install_conversation_api(monkeypatch, lost_response=True)
    args = (tmp_path, tmp_path / "company.yaml", "tenant_demo")
    with pytest.raises(httpx.ReadTimeout):
        terminal.converse("ask", None, "Prepare report", *args)
    with pytest.raises(ValueError, match="uncertain delivery"):
        terminal.converse("ask", None, "Different message", *args)
    terminal.converse("ask", None, "Prepare report", *args)
    posts = [item[2] for item in calls if item[1].endswith("/messages")]
    assert len(posts) == 2 and posts[0] == posts[1]
    state = json.loads(next((tmp_path / ".local").glob("conversation-*.json")).read_text())
    assert "pending" not in state


def test_chat_returns_prompt_when_reply_is_still_pending(tmp_path, monkeypatch, capsys):
    install_conversation_api(monkeypatch, pending=1)
    terminal.converse("ask", None, "Hello", tmp_path, tmp_path / "company.yaml",
                      "tenant_demo", wait_seconds=0)
    assert "background" in capsys.readouterr().out


def test_accepted_message_poll_failure_does_not_suggest_resending(tmp_path, monkeypatch, capsys):
    install_conversation_api(monkeypatch, failed_poll=True)
    terminal.converse("ask", None, "Hello", tmp_path, tmp_path / "company.yaml", "tenant_demo")
    assert "without resending" in capsys.readouterr().out


def test_conversation_guard_prevents_writes_for_other_tenant(tmp_path, monkeypatch):
    writes, _ = install_api(monkeypatch)
    with pytest.raises(ValueError, match="differs"):
        terminal.converse("ask", None, "Hello", tmp_path, tmp_path / "company.yaml", "other")
    assert writes == []
    assert not (tmp_path / ".local").exists()


def test_source_reads_only_explicit_bounded_text_and_task_commands_use_version(tmp_path, monkeypatch):
    calls = install_conversation_api(monkeypatch)
    args = (tmp_path, tmp_path / "company.yaml", "tenant_demo")
    terminal.converse("use", "conv_1", "", *args)
    source = tmp_path / "handbook.txt"
    source.write_text("Payment within 30 days.")
    terminal.converse("source", None, str(source), *args)
    assert calls[-1][2] == {"title": "handbook.txt", "content": "Payment within 30 days."}
    source.write_bytes(b"binary\x00data")
    with pytest.raises(ValueError, match="must be text"):
        terminal.converse("source", None, str(source), *args)
    for command, text in [("steer", "Focus on cost"), ("cancel", ""), ("resume", "Use new source")]:
        terminal.converse(command, "task_1", text, *args)
        assert calls[-1] == ("POST", f"/v1/tasks/task_1/{command}", {
            "expected_version": 3, "instruction": text,
        })
