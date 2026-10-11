from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from feya.domain import Contract, Money, OfferDraft, decimal_money, digest


class Fact(Contract):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,60}$")
    label: str = Field(min_length=1, max_length=80)
    kind: Literal["text", "date", "quantity", "service"] = "text"


class Rate(Contract):
    label: str
    unit_price: Money


class BusinessPack(Contract):
    api_version: Literal["feya.dev/v1alpha1"]
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]+$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    name: str
    description: str
    currency: Literal["EUR", "USD", "GBP"]
    tax_rate: str = Field(pattern=r"^0\.[0-9]{2}$")
    required_facts: list[Fact] = Field(min_length=1)
    rates: dict[str, Rate]
    default_outbound_dispatch: Literal["deny"]
    require_offer_approval: Literal[True]
    reply_intro: str
    fixture: dict[str, str]

    @model_validator(mode="after")
    def valid_fields(self):
        keys = [f.key for f in self.required_facts]
        if len(keys) != len(set(keys)) or not {"service", "quantity"} <= set(keys):
            raise ValueError("Pack requires distinct facts, including service and quantity")
        return self

    @property
    def fingerprint(self) -> str:
        return digest(self.model_dump())

    def quote(self, facts: dict[str, str], email: str) -> dict:
        if facts.get("service") not in self.rates:
            raise ValueError("Unsupported service: operator review required")
        quantity = facts.get("quantity", "")
        if not quantity.isascii() or not quantity.isdigit() or not 1 <= int(quantity) <= 999:
            raise ValueError("Quantity must be an integer from 1 to 999")
        rate = self.rates[facts["service"]]
        subtotal = Decimal(rate.unit_price) * int(quantity)
        tax = (subtotal * Decimal(self.tax_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return OfferDraft(
            customer_email=email,
            service=facts["service"],
            quantity=quantity,
            unit_price=rate.unit_price,
            subtotal=decimal_money(subtotal),
            tax=decimal_money(tax),
            total=decimal_money(subtotal + tax),
            currency=self.currency,
            rate_version=self.version,
        ).model_dump()


def load_company(path: Path) -> BusinessPack | None:
    return BusinessPack.model_validate(yaml.safe_load(path.read_text())) if path.exists() else None


def load_packs(directory: Path, company_file: Path | None = None) -> dict[str, BusinessPack]:
    packs = [
        BusinessPack.model_validate(yaml.safe_load(p.read_text()))
        for p in sorted(directory.glob("*.yaml"))
    ]
    if company_file is not None and (company := load_company(company_file)) is not None:
        packs.append(company)
    result = {p.id: p for p in packs}
    if not result or len(result) != len(packs):
        raise ValueError("Business packs missing or IDs duplicated")
    return result
