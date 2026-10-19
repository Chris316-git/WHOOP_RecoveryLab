"""Runtime settings as one explicit, immutable object.

Code that needs configuration takes a `Settings` argument instead of reading environment
variables at import time, so the same functions can run against another database, another
mail server or test doubles. `Settings.from_env()` builds the default from `.env` and the
process environment (GitHub Actions secrets arrive as environment variables).
"""
import os
from dataclasses import dataclass, field

from src import config  # noqa: F401  (loads .env into the environment)


@dataclass(frozen=True)
class SmtpSettings:
    host: str = "smtp.gmail.com"
    port: int = 465
    user: str = ""
    password: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.user and self.password)


@dataclass(frozen=True)
class Settings:
    database_url: str = ""
    token_store: str = "file"                 # "file" | "db"
    token_encryption_key: str = ""
    report_timezone: str = "America/Los_Angeles"
    report_email_to: str = ""
    google_calendar_ids: tuple[str, ...] = ("primary",)
    smtp: SmtpSettings = field(default_factory=SmtpSettings)
    public_base_url: str = ""                 # where the action endpoint is hosted, e.g. https://x.onrender.com
    action_signing_key: str = ""              # secret for signing the links in the email
    anthropic_api_key: str = ""               # optional: friendlier wording of the daily focus
    llm_model: str = "claude-haiku-5-5"
    reasoning_mode: str = "agent"             # agent (daily agent) | ai (one call) | shadow | off
    reasoning_model: str = "claude-sonnet-5-5"
    whoop_client_secret: str = ""             # also signs WHOOP's webhooks
    github_dispatch_token: str = ""           # web host only: starts the daily workflow on a WHOOP webhook
    github_repo: str = ""                     # e.g. owner/repo

    @property
    def actions_enabled(self) -> bool:
        return bool(self.public_base_url and self.action_signing_key)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        # Values pasted into a hosting dashboard often keep the quotes from .env; drop them.
        get = lambda k, d="": (env.get(k) or d).strip().strip("'\"").strip()  # noqa: E731
        return cls(
            database_url=get("DATABASE_URL"),
            token_store=get("TOKEN_STORE", "file").lower(),
            token_encryption_key=get("TOKEN_ENCRYPTION_KEY"),
            report_timezone=get("REPORT_TIMEZONE", "America/Los_Angeles"),
            report_email_to=get("REPORT_EMAIL_TO"),
            google_calendar_ids=tuple(c.strip() for c in get("GOOGLE_CALENDAR_IDS", "primary").split(",") if c.strip()),
            smtp=SmtpSettings(host=get("SMTP_HOST", "smtp.gmail.com"), port=int(get("SMTP_PORT", "465")),
                              user=get("SMTP_USER"), password=get("SMTP_PASSWORD")),
            public_base_url=get("PUBLIC_BASE_URL").rstrip("/"),
            action_signing_key=get("ACTION_SIGNING_KEY"),
            anthropic_api_key=get("ANTHROPIC_API_KEY"),
            llm_model=get("LLM_MODEL", "claude-haiku-5-5"),
            reasoning_mode=get("REASONING_MODE", "agent").lower(),
            reasoning_model=get("REASONING_MODEL", "claude-sonnet-5-5"),
            whoop_client_secret=get("WHOOP_CLIENT_SECRET"),
            github_dispatch_token=get("GITHUB_DISPATCH_TOKEN"),
            github_repo=get("GITHUB_REPO"),
        )

    def require(self, name: str) -> str:
        value = getattr(self, name)
        if not value:
            raise RuntimeError(f"Missing setting {name.upper()}. Check your .env file or GitHub Secrets.")
        return value
