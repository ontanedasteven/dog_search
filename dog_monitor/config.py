"""Environment-based configuration for the dog monitor application.

Designed for Cloud Run Jobs: all configuration comes from environment
variables (plain env vars for non-secrets, Secret Manager-mounted env vars
for EMAIL_PASSWORD in production). A local .env file is supported for
local development only (python-dotenv), and is not present in the
container image.
"""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised for fatal, application-halting configuration problems."""


@dataclass
class Config:
    email_from: Optional[str]
    email_to: Optional[str]
    email_password: Optional[str]
    headless: bool
    log_level: str
    firestore_project: Optional[str]
    firestore_database: Optional[str]

    @property
    def email_configured(self) -> bool:
        return bool(self.email_from and self.email_to and self.email_password)


def _parse_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in ("false", "0", "no", "off", "")


def load_config(env_path: Optional[str] = None) -> Config:
    """Load configuration from the environment (and a .env file if present
    -- used for local development; Cloud Run Jobs inject env vars directly).

    Only genuinely fatal problems raise ConfigError. Missing email
    credentials are NOT fatal here -- a scan should still run and store
    matches in Firestore even if alerting is not yet configured; alerts.py
    logs an error and leaves alert_sent=False for the next run in that case.
    """
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()

    headless = _parse_bool(os.getenv("HEADLESS", "true"), default=True)
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    # GOOGLE_CLOUD_PROJECT is set automatically inside Cloud Run; for local
    # development against the Firestore emulator, any non-empty project id
    # works (e.g. "demo-test") since the emulator does not check auth.
    firestore_project = (
        os.getenv("FIRESTORE_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT")
        or None
    )
    firestore_database = os.getenv("FIRESTORE_DATABASE_ID") or None

    return Config(
        email_from=os.getenv("EMAIL_FROM") or None,
        email_to=os.getenv("EMAIL_TO") or None,
        email_password=os.getenv("EMAIL_PASSWORD") or None,
        headless=headless,
        log_level=log_level,
        firestore_project=firestore_project,
        firestore_database=firestore_database,
    )
