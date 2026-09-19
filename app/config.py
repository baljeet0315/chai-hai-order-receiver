"""All settings come from environment variables (.env locally, Railway variables in production)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _digits(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


def _base_url(url: str) -> str:
    """Accepts the URL with or without the /rest/v1/ suffix Supabase shows on some pages."""
    url = url.strip().rstrip("/")
    return url.removesuffix("/rest/v1")


@dataclass(frozen=True)
class Settings:
    # Claude
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_workspace_id: str = os.getenv("ANTHROPIC_WORKSPACE_ID", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    # WhatsApp Cloud API
    wa_token: str = os.getenv("WHATSAPP_TOKEN", "")
    wa_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    wa_verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    wa_app_secret: str = os.getenv("WHATSAPP_APP_SECRET", "")
    wa_api_version: str = os.getenv("WHATSAPP_API_VERSION", "v21.0")
    wa_confirm_template: str = os.getenv("WHATSAPP_CONFIRM_TEMPLATE", "order_confirmed")
    wa_confirm_template_lang: str = os.getenv("WHATSAPP_CONFIRM_TEMPLATE_LANG", "en")
    # Reviewer (owner) WhatsApp number, digits only with country code, e.g. 16045551234
    owner_phone: str = _digits(os.getenv("OWNER_PHONE", ""))
    # Supabase
    supabase_url: str = _base_url(os.getenv("SUPABASE_URL", ""))
    supabase_key: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    # Google Sheets
    # Some hosts keep the surrounding quotes from a pasted .env line; strip them.
    google_service_account_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip().strip("'")
    google_sheet_id: str = os.getenv("GOOGLE_SHEET_ID", "")
    google_sheet_tab: str = os.getenv("GOOGLE_SHEET_TAB", "Orders")


settings = Settings()
