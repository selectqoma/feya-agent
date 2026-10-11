"""Small command shell over the same local API used by the browser."""

import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import httpx
from pydantic import TypeAdapter

from feya.conversation_models import ConversationMessage, SourceCreate
from feya.domain import Decision, Identifier
from feya.packs import load_company

PIXELS = ("11111", "11000", "11000", "11110", "11000", "11000", "11000")
HELP = """/setup, /onboard        Configure the local company and rates (stop app first)
/up [--skip-infra]      Start the workspace
/down                  Stop app processes; preserve data
/status                Check services and model configuration
/demo [--pack ID]       Create a synthetic enquiry; defaults to your company
/cases                 List recent cases
/case CASE_ID           Inspect facts, sources, actions and outcomes
/reply CASE_ID          Add the synthetic customer's reply
/approve CASE_ID        Review and approve one exact pending offer
/reject CASE_ID         Review and reject one exact pending offer
/recheck ACTION_ID      Queue provider reconciliation
/new [TITLE]           Start a conversation
/conversations         List conversations
/use CONVERSATION_ID   Select a saved conversation
/messages              Read the selected conversation
/source PATH           Attach an explicit UTF-8 text file
/work                  List delegated tasks
/task TASK_ID          Inspect progress and saved result
/steer TASK_ID TEXT     Change a task objective
/cancel TASK_ID         Cancel a task
/resume TASK_ID TEXT    Resume with additional instructions
Type naturally         Talk to Feya and delegate work
/help                  Show commands
/exit                  Leave the terminal; services keep running"""
COMMANDS = {
    "setup",
    "onboard",
    "up",
    "down",
    "status",
    "demo",
    "cases",
    "case",
    "reply",
    "approve",
    "reject",
    "recheck",
    "help",
    "exit",
    "new", "conversations", "use", "messages", "source", "work",
    "task", "steer", "cancel", "resume",
}


def banner():
    unicode = "utf" in (sys.stdout.encoding or "").lower()
    pixel = "██" if unicode else "##"
    lines = ["".join(pixel if bit == "1" else "  " for bit in row) for row in PIXELS]
    color = sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.getenv("TERM") != "dumb"
    labels = [
        "FEYA",
        "Business operations",
        "",
        "Local simulation",
        "",
        "/setup to begin",
        "/help for commands",
    ]
    for line, label in zip(lines, labels, strict=True):
        mark = f"\033[38;5;114m{line}\033[0m" if color else line
        print(f"  {mark}   {label}")
    print()


def shell(root: Path):
    banner()
    try:
        import readline

        def complete(text, state):
            matches = [
                "/" + command for command in sorted(COMMANDS) if ("/" + command).startswith(text)
            ]
            return matches[state] if state < len(matches) else None

        readline.set_completer_delims(" \t\n")
        readline.set_completer(complete)
        readline.parse_and_bind("tab: complete")
    except ImportError:
        pass
    while True:
        try:
            line = input("feya > ").strip()
            if not line:
                continue
            if not line.startswith("/"):
                subprocess.run(
                    [sys.executable, "-m", "feya.cli", "ask", "--", line], cwd=root, check=False
                )
                continue
            words = shlex.split(line)
            command = words[0].removeprefix("/")
            if command == "exit":
                break
            if command == "help":
                print(HELP)
                continue
            if command not in COMMANDS:
                print("Use /help for available commands.")
                continue
            subprocess.run(
                [sys.executable, "-m", "feya.cli", command, *words[1:]], cwd=root, check=False
            )
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print("\nCommand cancelled. /exit leaves the terminal.")
        except (ValueError, OSError) as exc:
            print(f"Could not run command: {exc}")


def show(value):
    # JSON escapes terminal control characters in source text and model output.
    print(json.dumps(value, indent=2, ensure_ascii=True))


def review(case: dict, actions: list[dict]):
    show(
        {
            "case": case["id"],
            "subject": case["subject"],
            "status": case.get("phase"),
            "next": case.get("next_action"),
            "missing": case.get("missing", []),
        }
    )
    print("\nFacts and their sources")
    show(case["facts"])
    print("\nSource messages")
    for source in case["evidence"]:
        show(
            {
                "source": source["id"],
                **{key: source["content"][key] for key in ("sender", "subject", "body")},
            }
        )
    print("\nActions")
    for action in actions:
        show({key: action[key] for key in ("id", "status", "payload")})
    if case.get("verifications"):
        print("\nProvider read-back")
        for result in case["verifications"]:
            show({key: result[key] for key in ("passed", "checked_fields")})


@contextmanager
def workspace_api(company_file: Path, tenant_id: str):
    company = load_company(company_file)
    with httpx.Client(
        base_url="http://127.0.0.1:8010/v1/",
        headers={"X-Feya-Local": "1"},
        timeout=10,
        trust_env=False,
    ) as client:

        def request(path, body=None):
            response = client.get(path) if body is None else client.post(path, json=body)
            response.raise_for_status()
            return response.json()

        workspace = request("workspace")
        if workspace["tenant_id"] != tenant_id:
            raise ValueError(
                "Running workspace differs from local configuration. Run /down then /up."
            )
        running_company = workspace.get("company_pack_id")
        expected_company = company.id if company else None
        if running_company != expected_company or (
            company
            and not any(
                pack["id"] == company.id and pack["fingerprint"] == company.fingerprint
                for pack in workspace["packs"]
            )
        ):
            raise ValueError("Running company setup is stale. Run /down then /up.")
        yield request, expected_company


def operate(command: str, identifier: str | None, company_file: Path, tenant_id: str):
    if identifier is not None:
        TypeAdapter(Identifier).validate_python(identifier)
    with workspace_api(company_file, tenant_id) as (request, expected_company):
        if command == "cases":
            cases = request("cases")
            if not cases:
                print("No cases yet. Use /demo to create a synthetic enquiry.")
            for case in cases:
                show({key: case[key] for key in ("id", "subject", "phase", "next_action")})
        elif command == "demo":
            pack_id = identifier or expected_company or "generic_enquiry"
            show(request("demo/" + pack_id, {}))
        elif command == "case":
            case = request("cases/" + str(identifier))
            review(case, case["actions"])
        elif command == "reply":
            show(request(f"cases/{identifier}/demo-reply", {}))
        elif command == "recheck":
            show(request(f"action-intents/{identifier}/reconcile", {}))
            print("Reconciliation queued. Inspect the case for the verified outcome.")
        elif command in {"approve", "reject"}:
            case = request("cases/" + str(identifier))
            pending = [a for a in case["actions"] if a["status"] == "awaiting_approval"]
            if len(pending) != 1:
                raise ValueError(
                    "Case must have exactly one pending approval; inspect it with /case."
                )
            action = pending[0]
            review(case, [action])
            print("This decision applies only to the exact action displayed above.")
            if input(f'Type "{command}" to continue, or Enter to cancel: ').strip() != command:
                print("Cancelled; no decision submitted.")
                return
            decision = Decision(
                decision="approve" if command == "approve" else "reject",
                expected_digest=action["digest"],
                reason=input("Reason for your decision: ").strip(),
            )
            show(request(f"approvals/{action['id']}/decide", decision.model_dump()))
            print("Decision recorded. Inspect the case for execution and provider verification.")


def save_session(path: Path, state: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(state, stream)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def converse(command: str, identifier: str | None, text: str, root: Path,
             company_file: Path, tenant_id: str, *, wait_seconds: float = 20):
    if command in {"use", "task", "steer", "cancel", "resume"}:
        TypeAdapter(Identifier).validate_python(identifier)
    filename = "conversation-" + hashlib.sha256(tenant_id.encode()).hexdigest() + ".json"
    state_path = root / ".local" / filename
    with workspace_api(company_file, tenant_id) as (request, _):
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        conversation_id = state.get("conversation_id")
        if conversation_id:
            TypeAdapter(Identifier).validate_python(conversation_id)
        if command in {"conversations", "work"}:
            show(request("conversations" if command == "conversations" else "tasks"))
            return
        if command == "task":
            show(request(f"tasks/{identifier}"))
            return
        if command in {"steer", "cancel", "resume"}:
            task = request(f"tasks/{identifier}")
            show(request(f"tasks/{identifier}/{command}", {
                "expected_version": task["version"], "instruction": text,
            }))
            return
        if command == "new":
            if state.get("pending"):
                raise ValueError("A message has uncertain delivery. Repeat that message before /new.")
            conversation = request("conversations", {"title": text or "New conversation"})
            save_session(state_path, {"conversation_id": conversation["id"]})
            show(conversation)
            return
        if command == "use":
            if state.get("pending"):
                raise ValueError("A message has uncertain delivery. Repeat that message before /use.")
            conversation = request(f"conversations/{identifier}")
            save_session(state_path, {"conversation_id": conversation["id"]})
            show(conversation)
            return
        if not conversation_id:
            if command != "ask":
                raise ValueError("Select a conversation with /new or /use first.")
            conversation = request("conversations", {"title": text[:160] or "New conversation"})
            conversation_id = conversation["id"]
            state = {"conversation_id": conversation_id}
            save_session(state_path, state)
        if command == "messages":
            show(request(f"conversations/{conversation_id}"))
        elif command == "source":
            path = Path(text).expanduser()
            if not path.is_file():
                raise ValueError("Source must be an explicit UTF-8 text file.")
            with path.open("rb") as stream:
                raw = stream.read(48001)
            if len(raw) > 48000 or b"\x00" in raw:
                raise ValueError("Source must be text with at most 12,000 characters.")
            source = SourceCreate(title=path.name, content=raw.decode("utf-8"))
            show(request(f"conversations/{conversation_id}/sources", source.model_dump()))
        elif command == "ask":
            pending = state.get("pending")
            if pending and pending["content"] != text:
                raise ValueError(
                    "Previous message has uncertain delivery. Use /messages, then repeat the exact "
                    "previous message to safely resolve it before sending another."
                )
            message = ConversationMessage(
                content=text, request_id=pending["request_id"] if pending else "req_" + uuid.uuid4().hex
            )
            state["pending"] = message.model_dump()
            save_session(state_path, state)
            try:
                receipt = request(f"conversations/{conversation_id}/messages", message.model_dump())
            except httpx.HTTPStatusError as exc:
                if 400 <= exc.response.status_code < 500:
                    state.pop("pending")
                    save_session(state_path, state)
                raise
            state.pop("pending")
            save_session(state_path, state)
            print(f"Message accepted in {conversation_id}. /messages reads later replies.")
            deadline = time.monotonic() + wait_seconds
            while True:
                try:
                    conversation = request(f"conversations/{conversation_id}")
                except httpx.HTTPError:
                    print("Message accepted; reply check unavailable. Use /messages without resending.")
                    return
                messages = conversation["messages"]
                replies = [item for item in messages if item.get("reply_to") == receipt["message_id"]]
                if replies:
                    for item in replies:
                        show(item)
                    return
                if not conversation.get("pending"):
                    origin = next(m["sequence"] for m in messages if m["id"] == receipt["message_id"])
                    for item in messages:
                        if item["sequence"] > origin and item["role"] != "user":
                            show(item)
                    return
                if time.monotonic() >= deadline:
                    print("Still working in the background. Use /messages or /work for progress.")
                    return
                time.sleep(min(0.5, max(0, deadline - time.monotonic())))
