"""Local company configuration; no model calls or provider credentials."""

import os
import re
import tempfile
from pathlib import Path
from uuid import uuid4

import yaml

from feya.packs import BusinessPack, load_company, load_packs


def ask(label: str, default: str = "", *, pattern: str = r"[^\x00-\x1f\x7f]{1,120}") -> str:
    while True:
        value = input(f"{label}{' [' + default + ']' if default else ''}: ").strip() or default
        if value.isprintable() and re.fullmatch(pattern, value):
            return value
        print("Please enter a valid value; Ctrl-C cancels without saving.")


def save_company(path: Path, pack: BusinessPack, expected: str | None):
    current = load_company(path)
    if (current.fingerprint if current else None) != expected:
        raise ValueError("Company setup changed while you were editing. Run /setup again.")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace atomically so interruption cannot leave a partial company pack.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            yaml.safe_dump(pack.model_dump(), file, sort_keys=False, allow_unicode=True)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def require_stopped(root: Path):
    for name in ("api", "worker", "gateway", "agent"):
        pidfile = root / ".local" / f"{name}.pid"
        if not pidfile.exists():
            continue
        try:
            os.kill(int(pidfile.read_text()), 0)
        except ProcessLookupError:
            continue
        raise ValueError("Stop the local app with /down (or feya down) before company setup.")


def setup(root: Path, company_file: Path, pack_dir: Path):
    require_stopped(root)
    current = load_company(company_file)
    templates = load_packs(pack_dir)
    print("Company setup · local simulation only")
    print("Configures this workspace; it does not create production access or connect providers.")
    if current:
        print("Editing the existing company. Changed rules invalidate its pending proposals.")
        template = current
    else:
        for pack in templates.values():
            print(f"  {pack.id}: {pack.name}")
        template_id = ask("Workflow template", next(iter(templates)))
        while template_id not in templates:
            template_id = ask("Choose one of the listed template IDs")
        template = templates[template_id]
    name = ask("Company name", current.name if current else "")
    currency = ask("Currency (EUR, USD, GBP)", template.currency, pattern="EUR|USD|GBP")
    tax = ask("Tax fraction (0.21 means 21%)", template.tax_rate, pattern=r"0\.[0-9]{2}")
    data = template.model_dump()
    for rate in data["rates"].values():
        rate["unit_price"] = ask(
            f"{rate['label']} unit price in {currency} (two decimals)",
            rate["unit_price"],
            pattern=r"(0|[1-9][0-9]{0,7})\.[0-9]{2}",
        )
    data.update(name=name, currency=currency, tax_rate=tax)
    if current and data == current.model_dump():
        print("Setup is unchanged; existing proposals keep their configuration version.")
        return
    version = current.version.split(".") if current else ["0", "1", "-1"]
    version[-1] = str(int(version[-1]) + 1)
    data.update(
        id=current.id if current else "company_" + uuid4().hex[:12],
        version=".".join(version),
        name=name,
        currency=currency,
        tax_rate=tax,
    )
    pack = BusinessPack.model_validate(data)
    print(f"\nCompany: {name}\nCurrency: {currency} · tax: {int(tax[-2:])}%")
    print("Required facts: " + ", ".join(f.label for f in pack.required_facts))
    for rate in pack.rates.values():
        print(f"  {rate.label}: {rate.unit_price} {currency}")
    print("Offers require your approval. Dispatch stays disabled. Model account is unchanged.")
    if input("Save this local company setup? [y/N]: ").strip().lower() != "y":
        print("Cancelled; no company configuration changed.")
        return
    require_stopped(root)
    save_company(company_file, pack, current.fingerprint if current else None)
    print(f"Saved {company_file}. Start with /up, then /demo to try a synthetic company case.")
