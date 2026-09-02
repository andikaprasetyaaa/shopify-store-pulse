from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import pytest

from shopify.client import (
    ReadOnlyViolation,
    ShopifyClient,
    ShopifyGraphQLError,
)
from shopify.config import ShopifyConfig


def make_config() -> ShopifyConfig:
    return ShopifyConfig(
        shop="wooden-ships",
        client_id="test-client-id",
        client_secret="test-client-secret",
        api_version="2026-07",
    )


def test_client_exposes_no_write_methods() -> None:
    client = ShopifyClient(
        make_config()
    )

    try:
        assert hasattr(
            client,
            "query",
        )

        for method_name in (
            "mutate",
            "mutation",
            "create",
            "update",
            "delete",
        ):
            assert not hasattr(
                client,
                method_name,
            )

    finally:
        client.close()


@pytest.mark.parametrize(
    "operation",
    [
        (
            "mutation UpdateProduct { "
            'productUpdate(product: {id: "x"}) '
            "{ userErrors { message } } "
            "}"
        ),
        (
            "subscription Example { "
            "shop { name } "
            "}"
        ),
    ],
)
def test_non_read_operations_are_blocked_before_http(
    operation: str,
) -> None:
    request_count = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal request_count

        request_count += 1

        return httpx.Response(
            500
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(
            handler
        )
    )

    client = ShopifyClient(
        make_config(),
        http_client=http_client,
    )

    try:
        with pytest.raises(
            ReadOnlyViolation
        ):
            client.query(
                operation
            )

        assert request_count == 0

    finally:
        http_client.close()


def test_query_gets_token_and_calls_graphql_with_token_header(
) -> None:
    token_calls = 0
    graphql_calls = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal token_calls
        nonlocal graphql_calls

        if (
            request.url.path
            == "/admin/oauth/access_token"
        ):
            token_calls += 1

            form = parse_qs(
                request.content.decode()
            )

            assert form[
                "grant_type"
            ] == [
                "client_credentials"
            ]

            assert form[
                "client_id"
            ] == [
                "test-client-id"
            ]

            assert form[
                "client_secret"
            ] == [
                "test-client-secret"
            ]

            return httpx.Response(
                200,
                json={
                    "access_token":
                        "test-access-token",
                    "scope": (
                        "read_inventory,"
                        "read_locations,"
                        "read_orders,"
                        "read_products,"
                        "read_reports"
                    ),
                    "expires_in":
                        86399,
                },
            )

        if (
            request.url.path
            == (
                "/admin/api/"
                "2026-07/"
                "graphql.json"
            )
        ):
            graphql_calls += 1

            assert (
                request.headers[
                    "X-Shopify-Access-Token"
                ]
                == "test-access-token"
            )

            body = json.loads(
                request.content
            )

            assert "query" in body

            assert body[
                "variables"
            ] == {}

            return httpx.Response(
                200,
                json={
                    "data": {
                        "shop": {
                            "name":
                                "Wooden Ships",
                        }
                    }
                },
            )

        return httpx.Response(
            404
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(
            handler
        )
    )

    client = ShopifyClient(
        make_config(),
        http_client=http_client,
    )

    try:
        query = (
            "query GetShop { "
            "shop { name } "
            "}"
        )

        first_result = client.query(
            query
        )

        second_result = client.query(
            query
        )

        assert (
            first_result[
                "shop"
            ][
                "name"
            ]
            == "Wooden Ships"
        )

        assert (
            second_result[
                "shop"
            ][
                "name"
            ]
            == "Wooden Ships"
        )

        # Access token should be reused
        # until it approaches expiry.
        assert token_calls == 1

        assert graphql_calls == 2

    finally:
        http_client.close()


def test_graphql_errors_raise_exception(
) -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:

        if (
            request.url.path
            == "/admin/oauth/access_token"
        ):
            return httpx.Response(
                200,
                json={
                    "access_token":
                        "test-access-token",
                    "expires_in":
                        86399,
                },
            )

        return httpx.Response(
            200,
            json={
                "errors": [
                    {
                        "message":
                            "Access denied.",
                    }
                ]
            },
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(
            handler
        )
    )

    client = ShopifyClient(
        make_config(),
        http_client=http_client,
    )

    try:
        with pytest.raises(
            ShopifyGraphQLError,
            match="Access denied",
        ):
            client.query(
                "query GetShop { "
                "shop { name } "
                "}"
            )

    finally:
        http_client.close()