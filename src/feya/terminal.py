"""Small command shell over the same local API used by the browser."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import httpx
from pydantic import TypeAdapter

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
            words = shlex.split(line)
            command = words[0].removeprefix("/")
            if command == "exit":
                break
            if command == "help":
                print(HELP)
                continue
            if command not in COMMANDS:
                print("Use /help for available commands. Natural-language chat is not implemented.")
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


def operate(command: str, identifier: str | None, company_file: Path, tenant_id: str):
    if identifier is not None:
        TypeAdapter(Identifier).validate_python(identifier)
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
