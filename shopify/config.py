from __future__ import annotations

import os
import re

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class ShopifyConfig(BaseModel):
    """
    Validated Shopify configuration.

    Source of truth:
    - SHOPIFY_SHOP
    - SHOPIFY_CLIENT_ID
    - SHOPIFY_CLIENT_SECRET
    - SHOPIFY_API_VERSION
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    shop: str = Field(min_length=1)
    client_id: str = Field(min_length=1)
    client_secret: SecretStr
    api_version: str = Field(min_length=1)

    @field_validator("shop")
    @classmethod
    def normalize_shop(cls, value: str) -> str:
        shop = value.strip().lower()

        shop = re.sub(r"^https?://", "", shop)
        shop = shop.rstrip("/")

        if shop.endswith(".myshopify.com"):
            shop = shop[: -len(".myshopify.com")]

        if "/" in shop:
            raise ValueError(
                "SHOPIFY_SHOP must be a shop slug such as "
                "'wooden-ships' or a myshopify.com domain."
            )

        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", shop):
            raise ValueError(
                "SHOPIFY_SHOP contains unsupported characters."
            )

        return shop

    @field_validator("client_id")
    @classmethod
    def validate_client_id(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "SHOPIFY_CLIENT_ID cannot be empty."
            )

        return value

    @field_validator("client_secret")
    @classmethod
    def validate_client_secret(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError(
                "SHOPIFY_CLIENT_SECRET cannot be empty."
            )

        return value

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, value: str) -> str:
        value = value.strip()

        match = re.fullmatch(
            r"(\d{4})-(\d{2})",
            value,
        )

        if not match:
            raise ValueError(
                "SHOPIFY_API_VERSION must use YYYY-MM format, "
                "for example 2026-07."
            )

        if match.group(2) not in {
            "01",
            "04",
            "07",
            "10",
        }:
            raise ValueError(
                "SHOPIFY_API_VERSION must use a Shopify "
                "quarterly version: 01, 04, 07, or 10."
            )

        return value

    @property
    def shop_domain(self) -> str:
        return f"{self.shop}.myshopify.com"

    @property
    def token_url(self) -> str:
        return (
            f"https://{self.shop_domain}"
            "/admin/oauth/access_token"
        )

    @property
    def graphql_url(self) -> str:
        return (
            f"https://{self.shop_domain}"
            f"/admin/api/{self.api_version}/graphql.json"
        )

    @classmethod
    def from_env(cls) -> "ShopifyConfig":
        env_path = find_dotenv(usecwd=True)

        if env_path:
            load_dotenv(
                env_path,
                override=False,
            )

        return cls(
            shop=os.getenv(
                "SHOPIFY_SHOP",
                "",
            ),
            client_id=os.getenv(
                "SHOPIFY_CLIENT_ID",
                "",
            ),
            client_secret=os.getenv(
                "SHOPIFY_CLIENT_SECRET",
                "",
            ),
            api_version=os.getenv(
                "SHOPIFY_API_VERSION",
                "",
            ),
        )