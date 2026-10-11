import argparse
import asyncio
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / ".local"


def load_environment():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def init():
    LOCAL.mkdir(exist_ok=True)
    env = ROOT / ".env"
    if not env.exists():
        env.write_text(
            f"FEYA_GATEWAY_TOKEN={secrets.token_urlsafe(32)}\nFEYA_AGENT_TOKEN={secrets.token_urlsafe(32)}\nFEYA_RUNNER=fixture\nFEYA_LOCAL_DEMO=1\n"
        )
        env.chmod(0o600)
    print("Local configuration ready. No external provider connected.")


def compose(*args):
    command = ["docker", "compose", "-f", str(ROOT / "deploy/compose.yaml"), *args]
    subprocess.run(command, cwd=ROOT, check=True, timeout=240)


def up(skip_infra=False):
    init()
    load_environment()
    if not skip_infra:
        compose("up", "-d")
    from sqlalchemy import text

    from feya.config import settings
    from feya.db import make_engine

    engine = make_engine(settings.database_url)
    deadline = time.monotonic() + 45
    while True:
        try:
            with engine.connect() as db:
                db.execute(text("SELECT 1"))
            break
        except Exception:
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "PostgreSQL is unavailable; inspect docker compose logs"
                ) from None
            time.sleep(1)
    engine.dispose()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True)
    if not (ROOT / "apps/console/dist/index.html").exists():
        subprocess.run(["npm", "ci"], cwd=ROOT / "apps/console", check=True)
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "apps/console", check=True)
    services = {
        "gateway": [
            "-m",
            "uvicorn",
            "feya.gateway:create_gateway_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "8011",
        ],
        "agent": [
            "-m",
            "uvicorn",
            "feya.agents:create_agent_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "8012",
        ],
        "api": [
            "-m",
            "uvicorn",
            "feya.api:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "8010",
        ],
        "worker": ["-m", "feya.worker"],
    }
    for name, args in services.items():
        pidfile = LOCAL / f"{name}.pid"
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), 0)
                print(f"{name}: already running")
                continue
            except ProcessLookupError:
                pidfile.unlink()
        env = dict(os.environ)
        if name == "agent":
            allowed = {
                "PATH",
                "HOME",
                "TMPDIR",
                "LANG",
                "FEYA_AGENT_TOKEN",
                "FEYA_RUNNER",
                "FEYA_MODEL",
                "CODEX_HOME",
            }
            if settings.runner == "pydantic-ai" and not settings.model.startswith("openai-codex:"):
                allowed |= {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
            env = {key: value for key, value in env.items() if key in allowed}
        elif name == "api":
            env.pop("FEYA_GATEWAY_TOKEN", None)
            env.pop("FEYA_AGENT_TOKEN", None)
        with (LOCAL / f"{name}.log").open("ab") as log:
            process = subprocess.Popen(
                [sys.executable, *args],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        pidfile.write_text(str(process.pid))
    print("Feya: http://127.0.0.1:8010\nTemporal: http://127.0.0.1:58233\nLogs: .local/*.log")


def down():
    for name in ("worker", "api", "agent", "gateway"):
        pidfile = LOCAL / f"{name}.pid"
        if pidfile.exists():
            pid = int(pidfile.read_text())
            # A stale PID file must never kill an unrelated process.
            command = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True
            ).stdout
            if "feya." in command:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            pidfile.unlink()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        running = (
            subprocess.run(
                [
                    "pgrep",
                    "-f",
                    str(ROOT / ".venv/bin/python") + r".*feya\.(worker|api|agents|gateway)",
                ],
                capture_output=True,
            ).returncode
            == 0
        )
        if not running:
            break
        time.sleep(0.2)
    print("Feya application stopped. Database and Temporal volumes are retained.")


async def doctor():
    import httpx
    from sqlalchemy import text
    from temporalio.client import Client

    from feya.config import settings
    from feya.db import make_engine

    checks = {}
    try:
        engine = make_engine(settings.database_url)
        with engine.connect() as db:
            db.execute(text("SELECT 1"))
        engine.dispose()
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unavailable"
    try:
        client = await Client.connect(settings.temporal_address)
        checks["temporal"] = "ok" if await client.service_client.check_health() else "unavailable"
    except Exception:
        checks["temporal"] = "unavailable"
    async with httpx.AsyncClient(timeout=5) as http:
        try:
            checks["api"] = (await http.get("http://127.0.0.1:8010/health")).json()["status"]
        except Exception:
            checks["api"] = "unavailable"
    checks["runner"] = settings.runner
    checks["model"] = settings.model or "fixture:deterministic-v1"
    checks["claude_cli"] = "installed" if shutil.which("claude") else "not installed"
    checks["codex_cli"] = "installed" if shutil.which("codex") else "not installed"
    print(json.dumps(checks, indent=2))
    return all(checks[k] == "ok" for k in ("postgres", "temporal", "api"))


def main():
    parser = argparse.ArgumentParser(prog="feya")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init").add_argument("--demo", action="store_true")
    sub.add_parser("up").add_argument("--skip-infra", action="store_true")
    sub.add_parser("down")
    sub.add_parser("doctor")
    sub.add_parser("demo").add_argument("--pack", default="generic_enquiry")
    pack = sub.add_parser("pack")
    pack.add_argument("action", choices=["validate"])
    pack.add_argument("directory", nargs="?", default="packs")
    sub.add_parser("test")
    args = parser.parse_args()
    load_environment()
    if args.command == "init":
        init()
    elif args.command == "up":
        up(args.skip_infra)
    elif args.command == "down":
        down()
    elif args.command == "doctor":
        sys.exit(0 if asyncio.run(doctor()) else 1)
    elif args.command == "pack":
        from feya.packs import load_packs

        packs = load_packs(Path(args.directory))
        print("Validated: " + ", ".join(f"{p.id}@{p.version}" for p in packs.values()))
    elif args.command == "demo":
        import httpx

        response = httpx.post(
            "http://127.0.0.1:8010/v1/demo/" + args.pack, json={}, headers={"X-Feya-Local": "1"}
        )
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))
    elif args.command == "test":
        sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT))
