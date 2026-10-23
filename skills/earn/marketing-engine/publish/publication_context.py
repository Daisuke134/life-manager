"""Resolve a publication route from the registry or an explicit Factory context."""

from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class PublishContext:
    account: dict
    product: dict
    destination_url: str


def resolve_publication_route(*, engine: pathlib.Path, account_id: str,
                              product_id: str | None = None,
                              context: PublishContext | None = None) -> tuple[dict, dict | None]:
    if context is not None:
        if account_id != context.account.get("account_id"):
            raise ValueError("publication context account mismatch")
        if product_id is not None and product_id != context.product.get("product_id"):
            raise ValueError("publication context product mismatch")
        if context.account.get("product_id") != context.product.get("product_id"):
            raise ValueError("publication context account product mismatch")
        return context.account, context.product
    gates = pathlib.Path(engine) / "gates"
    if str(gates) not in sys.path:
        sys.path.insert(0, str(gates))
    from product_router import load_registry

    registry = load_registry(engine)
    if product_id is not None and product_id not in registry.products:
        raise ValueError("publication product unknown")
    if account_id not in registry.accounts:
        raise ValueError("publication account unknown")
    return registry.accounts[account_id], (registry.products[product_id]
                                           if product_id is not None else None)


def require_exact_destination(caption: str, destination_url: str) -> None:
    matches = [token for token in caption.split() if destination_url in token]
    if not destination_url or matches != [destination_url]:
        raise ValueError("publication destination URL must appear exactly once as a complete token")
