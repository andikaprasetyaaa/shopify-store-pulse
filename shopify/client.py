from __future__ import annotations

import re
import time
from collections.abc import Mapping
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from shopify.config import ShopifyConfig


class ShopifyError(RuntimeError):
    """
    Base exception for Shopify client failures.
    """


class ShopifyAuthError(ShopifyError):
    """
    Authentication or authorization failure.
    """


class ShopifyGraphQLError(ShopifyError):
    """
    Shopify GraphQL returned one or more errors.
    """


class ReadOnlyViolation(ShopifyError):
    """
    Raised when code attempts a non-read GraphQL operation.
    """


class _RetryableShopifyError(ShopifyError):
    """
    Internal exception for retryable HTTP responses.
    """


class ShopifyClient:
    """
    Read-only Shopify Admin GraphQL client.

    Application code only receives query().

    Access tokens are acquired internally using
    Shopify client credentials.

    GraphQL mutation and subscription operations
    are rejected before any HTTP request is made.
    """

    def __init__(
        self,
        config: ShopifyConfig,
        *,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.config = config

        self._owns_http_client = (
            http_client is None
        )

        self._http = (
            http_client
            or httpx.Client(
                timeout=timeout_seconds,
            )
        )

        self._access_token: str | None = None
        self._token_refresh_at: float = 0.0

    def __enter__(
        self,
    ) -> "ShopifyClient":
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_http_client:
            self._http.close()

    def query(
        self,
        document: str,
        variables: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a read-only Shopify GraphQL query.

        Returns only the GraphQL data object.

        mutation and subscription operations are
        blocked before authentication or network access.
        """

        self._assert_read_only(document)

        access_token = (
            self._get_access_token()
        )

        response = self._post(
            self.config.graphql_url,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": access_token,
            },
            json={
                "query": document,
                "variables": dict(
                    variables or {}
                ),
            },
        )

        if response.status_code == 401:
            self._clear_cached_token()

            raise ShopifyAuthError(
                "Shopify rejected the access token "
                "with HTTP 401."
            )

        if response.status_code == 403:
            raise ShopifyAuthError(
                "Shopify rejected the request "
                "with HTTP 403. Check the app's "
                "granted access scopes."
            )

        if response.status_code >= 400:
            raise ShopifyError(
                "Shopify GraphQL request failed "
                f"with HTTP {response.status_code}."
            )

        try:
            payload = response.json()

        except ValueError as exc:
            raise ShopifyError(
                "Shopify returned a non-JSON "
                "GraphQL response."
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise ShopifyError(
                "Shopify returned an invalid "
                "GraphQL response."
            )

        errors = payload.get(
            "errors"
        )

        if errors:
            messages: list[str] = []

            for error in errors:
                if isinstance(
                    error,
                    dict,
                ):
                    messages.append(
                        str(
                            error.get(
                                "message",
                                "Unknown GraphQL error",
                            )
                        )
                    )

                else:
                    messages.append(
                        str(error)
                    )

            raise ShopifyGraphQLError(
                "; ".join(messages)
            )

        data = payload.get(
            "data"
        )

        if not isinstance(
            data,
            dict,
        ):
            raise ShopifyGraphQLError(
                "Shopify GraphQL response "
                "did not contain a data object."
            )

        return data

    def _get_access_token(
        self,
    ) -> str:
        """
        Return cached access token if still valid.

        Otherwise request a new token using
        client_credentials.
        """

        now = time.monotonic()

        if (
            self._access_token
            and now < self._token_refresh_at
        ):
            return self._access_token

        response = self._post(
            self.config.token_url,
            headers={
                "Content-Type":
                    "application/x-www-form-urlencoded",
            },
            data={
                "grant_type":
                    "client_credentials",
                "client_id":
                    self.config.client_id,
                "client_secret":
                    self.config.client_secret
                    .get_secret_value(),
            },
        )

        if response.status_code >= 400:
            raise ShopifyAuthError(
                "Shopify token request failed "
                f"with HTTP {response.status_code}."
            )

        try:
            payload = response.json()

        except ValueError as exc:
            raise ShopifyAuthError(
                "Shopify token endpoint returned "
                "a non-JSON response."
            ) from exc

        access_token = payload.get(
            "access_token"
        )

        if (
            not isinstance(
                access_token,
                str,
            )
            or not access_token
        ):
            raise ShopifyAuthError(
                "Shopify token response did not "
                "contain an access_token."
            )

        try:
            expires_in = int(
                payload.get(
                    "expires_in",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ShopifyAuthError(
                "Shopify token response contained "
                "an invalid expires_in value."
            ) from exc

        # Refresh one minute before expiry
        # when the token lifetime permits it.
        refresh_margin = (
            60
            if expires_in > 60
            else 0
        )

        self._access_token = access_token

        self._token_refresh_at = (
            time.monotonic()
            + max(
                expires_in - refresh_margin,
                0,
            )
        )

        return access_token

    def _clear_cached_token(
        self,
    ) -> None:
        self._access_token = None
        self._token_refresh_at = 0.0

    @retry(
        retry=retry_if_exception_type(
            (
                httpx.TransportError,
                _RetryableShopifyError,
            )
        ),
        wait=wait_exponential(
            multiplier=0.5,
            min=0.5,
            max=4,
        ),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _post(
        self,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Internal POST helper with retry for
        transport failures, HTTP 429 and HTTP 5xx.
        """

        response = self._http.post(
            url,
            **kwargs,
        )

        if (
            response.status_code == 429
            or response.status_code >= 500
        ):
            raise _RetryableShopifyError(
                "Retryable Shopify HTTP status: "
                f"{response.status_code}"
            )

        return response

    @staticmethod
    def _assert_read_only(
        document: str,
    ) -> None:
        """
        Reject mutation/subscription documents
        before any request reaches Shopify.
        """

        if (
            not isinstance(
                document,
                str,
            )
            or not document.strip()
        ):
            raise ValueError(
                "GraphQL document cannot be empty."
            )

        code = (
            ShopifyClient
            ._remove_graphql_strings_and_comments(
                document
            )
        )

        forbidden_operation = re.search(
            r"\b(?:mutation|subscription)\b",
            code,
            flags=re.IGNORECASE,
        )

        if forbidden_operation:
            raise ReadOnlyViolation(
                "Only GraphQL query operations "
                "are allowed. mutation and "
                "subscription are blocked."
            )

    @staticmethod
    def _remove_graphql_strings_and_comments(
        document: str,
    ) -> str:
        """
        Remove strings/comments before checking
        GraphQL operation keywords.

        This avoids treating words inside GraphQL
        string values or comments as operations.
        """

        without_block_strings = re.sub(
            r'"""[\s\S]*?"""',
            " ",
            document,
        )

        without_strings = re.sub(
            r'"(?:\\.|[^"\\])*"',
            " ",
            without_block_strings,
        )

        without_comments = re.sub(
            r"#.*$",
            " ",
            without_strings,
            flags=re.MULTILINE,
        )

        return without_comments