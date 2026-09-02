from __future__ import annotations

"""
Gemini configuration, validated the same way the
Shopify config is.
"""

import os
import re

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class AnalystConfigError(RuntimeError):
    """Raised when the analyst is not configured."""


class GeminiConfig(BaseModel):
    """
    Source of truth:
    - GEMINI_API_KEY
    - GEMINI_MODEL
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        # `model_name` would otherwise collide with
        # pydantic's own protected `model_` namespace.
        protected_namespaces=(),
    )

    api_key: SecretStr
    model_name: str = Field(min_length=1)
    api_version: str = "v1beta"

    @field_validator("api_key")
    @classmethod
    def validate_api_key(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError(
                "GEMINI_API_KEY cannot be empty."
            )

        return value

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        value = value.strip()

        # Guards against the whole model id being
        # pasted with a path prefix, and against a
        # value that would need URL escaping.
        value = value.removeprefix("models/")

        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*",
            value,
        ):
            raise ValueError(
                "GEMINI_MODEL must be a bare model id "
                "such as 'gemini-3.5-flash-lite'."
            )

        return value

    @property
    def generate_url(self) -> str:
        return (
            "https://generativelanguage.googleapis.com"
            f"/{self.api_version}/models/"
            f"{self.model_name}:generateContent"
        )

    @classmethod
    def from_env(cls) -> "GeminiConfig":
        env_path = find_dotenv(usecwd=True)

        if env_path:
            load_dotenv(
                env_path,
                override=False,
            )

        api_key = os.getenv(
            "GEMINI_API_KEY",
            "",
        ).strip()

        if not api_key:
            raise AnalystConfigError(
                "GEMINI_API_KEY is not set. Add it to "
                ".env - not .env.example, which is "
                "committed."
            )

        return cls(
            api_key=api_key,
            model_name=os.getenv(
                "GEMINI_MODEL",
                "gemini-3.5-flash-lite",
            ),
        )

    @classmethod
    def is_configured(cls) -> bool:
        try:
            cls.from_env()

        except (
            AnalystConfigError,
            ValueError,
        ):
            return False

        return True
