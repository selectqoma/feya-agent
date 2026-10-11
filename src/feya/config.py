import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "FEYA_DATABASE_URL", "postgresql+psycopg://feya:feya-local@127.0.0.1:55432/feya"
    )
    temporal_address: str = os.getenv("FEYA_TEMPORAL_ADDRESS", "127.0.0.1:57233")
    gateway_url: str = os.getenv("FEYA_GATEWAY_URL", "http://127.0.0.1:8011")
    agent_url: str = os.getenv("FEYA_AGENT_URL", "http://127.0.0.1:8012")
    gateway_token: str = os.getenv("FEYA_GATEWAY_TOKEN", "")
    agent_token: str = os.getenv("FEYA_AGENT_TOKEN", "")
    tenant_id: str = os.getenv("FEYA_TENANT_ID", "tenant_demo")
    pack_dir: Path = Path(os.getenv("FEYA_PACK_DIR", "packs"))
    console_dir: Path = Path(os.getenv("FEYA_CONSOLE_DIR", "apps/console/dist"))
    runner: str = os.getenv("FEYA_RUNNER", "fixture")
    model: str = os.getenv("FEYA_MODEL", "")
    local_demo: bool = os.getenv("FEYA_LOCAL_DEMO", "1") == "1"


settings = Settings()
