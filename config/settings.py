import os
from utils.logger import get_logger

logger = get_logger(__name__)
PROSPEO_API_BASE_URL = "https://api.prospeo.io"


class Settings:
    def __init__(self):
        self.OCEAN_API_TOKEN = self._load_env("OCEAN_API_TOKEN", aliases=["OCEAN_API_KEY"])
        self.PROSPEO_API_KEY = self._load_env("PROSPEO_API_KEY")
        self.BREVO_API_KEY = self._load_env("BREVO_API_KEY")
        self.BREVO_SENDER_EMAIL = self._load_env("BREVO_SENDER_EMAIL")

        self.OCEAN_BASE_URL = self._load_env("OCEAN_BASE_URL", default="https://api.ocean.io")
        self.PROSPEO_BASE_URL = self._load_env("PROSPEO_BASE_URL", default=PROSPEO_API_BASE_URL)
        self.BREVO_BASE_URL = self._load_env("BREVO_BASE_URL", default="https://api.brevo.com")

        self._normalize_prospeo_base_url()
        self._validate_required_settings()

    def _normalize_prospeo_base_url(self):
        lower = self.PROSPEO_BASE_URL.lower()
        if "app.prospeo.io" in lower or lower.endswith("/api"):
            logger.warning(
                "Detected legacy or incorrect PROSPEO_BASE_URL '%s'; normalizing to '%s'",
                self.PROSPEO_BASE_URL,
                PROSPEO_API_BASE_URL,
            )
            self.PROSPEO_BASE_URL = PROSPEO_API_BASE_URL
        if "example" in lower or "localhost" in lower:
            logger.warning(
                "PROSPEO_BASE_URL appears to be a placeholder or local value: %s",
                self.PROSPEO_BASE_URL,
            )
            self.PROSPEO_BASE_URL = PROSPEO_API_BASE_URL

    def _load_env(self, key: str, default: str = "", aliases=None) -> str:
        aliases = aliases or []
        value = os.getenv(key)
        if not value:
            for alt in aliases:
                value = os.getenv(alt)
                if value:
                    break
        if value is None:
            value = getattr(self, key, default)
        return str(value).strip()

    def _validate_required_settings(self):
        missing = [
            name for name in [
                "OCEAN_API_TOKEN",
                "PROSPEO_API_KEY",
                "BREVO_API_KEY",
                "BREVO_SENDER_EMAIL",
            ]
            if not getattr(self, name)
        ]

        if missing:
            raise ValueError(
                f"Missing required settings: {', '.join(missing)}. "
                "Set them in .env or the environment."
            )

        if "@" not in self.BREVO_SENDER_EMAIL:
            raise ValueError("BREVO_SENDER_EMAIL must be a valid email address")

        if any(token in self.PROSPEO_BASE_URL.lower() for token in ("example", "localhost")):
            logger.warning(
                "PROSPEO_BASE_URL appears to be a placeholder or local value: %s",
                self.PROSPEO_BASE_URL,
            )


def get_settings() -> Settings:
    return Settings()
