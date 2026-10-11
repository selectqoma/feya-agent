import os
from pathlib import Path

import pytest

from feya.db import make_engine
from feya.domain import Inbound, uid
from feya.gateway import FakeProvider, Gateway
from feya.packs import load_packs
from feya.service import Service


@pytest.fixture
def service():
    engine = make_engine(
        os.getenv(
            "FEYA_TEST_DATABASE_URL", "postgresql+psycopg://feya:feya-local@127.0.0.1:55432/feya"
        )
    )
    service = Service(engine, load_packs(Path("packs")), uid("test"))
    yield service
    engine.dispose()


@pytest.fixture
def gateway(service):
    return Gateway(service, FakeProvider(service.engine, service.tenant))


def enquiry(pack_id="generic_enquiry", *, complete=False, thread=None):
    packs = load_packs(Path("packs"))
    p = packs[pack_id]
    return Inbound(
        event_id=uid("event"),
        thread_id=thread or uid("thread"),
        pack_id=pack_id,
        sender=p.fixture["sender"],
        subject=p.fixture["subject"],
        body=p.fixture["body"] + ("\n" + p.fixture["reply"] if complete else ""),
    )
