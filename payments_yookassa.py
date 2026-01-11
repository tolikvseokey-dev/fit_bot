from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from yookassa import Configuration, Payment

@dataclass(frozen=True)
class YooKassaConfig:
    shop_id: str
    secret_key: str
    return_url: str

def init_yookassa(cfg: YooKassaConfig) -> None:
    Configuration.account_id = cfg.shop_id
    Configuration.secret_key = cfg.secret_key

def create_sbp_payment(
    *,
    cfg: YooKassaConfig,
    amount_rub: int,
    description: str,
    user_id: int,
    idempotency_key: str | None = None,
    webhook_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Creates a payment with Redirect confirmation. YooKassa will provide confirmation_url.
    Docs mention redirect to confirmation_url for user action. citeturn2search13
    """
    init_yookassa(cfg)

    idem = idempotency_key or str(uuid.uuid4())

    payload = {
        "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": cfg.return_url},
        "capture": True,
        "description": description,
        "metadata": {
            "telegram_user_id": str(user_id),
            **(webhook_meta or {}),
        },
    }

    payment = Payment.create(payload, idem)
    confirmation_url = getattr(payment, "confirmation", {}).get("confirmation_url")
    return {
        "id": payment.id,
        "status": payment.status,
        "confirmation_url": confirmation_url,
        "idempotency_key": idem,
        "raw": payment.json(),
    }

def fetch_payment_status(cfg: YooKassaConfig, payment_id: str) -> dict[str, Any]:
    init_yookassa(cfg)
    payment = Payment.find_one(payment_id)
    return {
        "id": payment.id,
        "status": payment.status,
        "paid": getattr(payment, "paid", None),
        "raw": payment.json(),
    }
