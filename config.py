import os
from dataclasses import dataclass

def _get(name: str, default: str | None = None) -> str:
    val = os.getenv(name, default)
    if val is None:
        raise RuntimeError(f"Missing env var: {name}")
    return val

@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_username: str

    db_path: str
    pdf_dir: str

    # Webhook server
    webhook_host: str
    webhook_port: int
    webhook_path: str
    webhook_secret: str | None

    # YooKassa
    yookassa_shop_id: str
    yookassa_secret_key: str
    yookassa_return_url: str

    # Open Food Facts
    off_enabled: bool
    off_timeout: int

def load_config() -> Config:
    return Config(
        bot_token=_get("BOT_TOKEN"),
        admin_username=os.getenv("ADMIN_USERNAME", "AnatoliiOsin"),

        db_path=os.getenv("DB_PATH", "kbju.sqlite3"),
        pdf_dir=os.getenv("PDF_DIR", "pdf_exports"),

        webhook_host=os.getenv("WEBHOOK_HOST", "0.0.0.0"),
        webhook_port=int(os.getenv("WEBHOOK_PORT", "8080")),
        webhook_path=os.getenv("WEBHOOK_PATH", "/yookassa/webhook"),
        webhook_secret=os.getenv("WEBHOOK_SECRET") or None,

        yookassa_shop_id=os.getenv("YOOKASSA_SHOP_ID", ""),
        yookassa_secret_key=os.getenv("YOOKASSA_SECRET_KEY", ""),
        yookassa_return_url=os.getenv("YOOKASSA_RETURN_URL", "https://example.com/return"),

        off_enabled=os.getenv("OFF_ENABLED", "1").strip() not in ("0", "false", "False"),
        off_timeout=int(os.getenv("OFF_TIMEOUT", "8")),
    )
