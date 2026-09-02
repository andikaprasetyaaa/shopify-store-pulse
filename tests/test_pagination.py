from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from shopify.pagination import (
    PaginationError,
    paginate_connection,
)


class FakeClient:
    def __init__(
        self,
        pages: dict[
            str | None,
            dict[str, Any],
        ],
    ) -> None:
        self.pages = pages

        self.calls: list[
            dict[str, Any]
        ] = []

    def query(
        self,
        document: str,
        variables: Mapping[
            str,
            Any,
        ] | None = None,
    ) -> dict[str, Any]:
        values = dict(
            variables or {}
        )

        self.calls.append(
            values
        )

        cursor = values.get(
            "after"
        )

        return self.pages[
            cursor
        ]


def test_pagination_collects_all_pages(
) -> None:
    client = FakeClient(
        {
            None: {
                "productVariants": {
                    "nodes": [
                        {
                            "id":
                                "variant-1"
                        },
                        {
                            "id":
                                "variant-2"
                        },
                    ],
                    "pageInfo": {
                        "hasNextPage":
                            True,
                        "endCursor":
                            "cursor-1",
                    },
                }
            },

            "cursor-1": {
                "productVariants": {
                    "nodes": [
                        {
                            "id":
                                "variant-3"
                        },
                    ],
                    "pageInfo": {
                        "hasNextPage":
                            False,
                        "endCursor":
                            None,
                    },
                }
            },
        }
    )

    nodes = list(
        paginate_connection(
            client,
            "query Test {}",
            "productVariants",
            page_size=2,
        )
    )

    assert nodes == [
        {
            "id":
                "variant-1"
        },
        {
            "id":
                "variant-2"
        },
        {
            "id":
                "variant-3"
        },
    ]

    assert client.calls == [
        {
            "first": 2,
            "after": None,
        },
        {
            "first": 2,
            "after":
                "cursor-1",
        },
    ]


def test_max_items_stops_early(
) -> None:
    client = FakeClient(
        {
            None: {
                "productVariants": {
                    "nodes": [
                        {
                            "id":
                                "variant-1"
                        },
                        {
                            "id":
                                "variant-2"
                        },
                        {
                            "id":
                                "variant-3"
                        },
                    ],
                    "pageInfo": {
                        "hasNextPage":
                            True,
                        "endCursor":
                            "cursor-1",
                    },
                }
            },

            "cursor-1": {
                "productVariants": {
                    "nodes": [
                        {
                            "id":
                                "variant-4"
                        },
                    ],
                    "pageInfo": {
                        "hasNextPage":
                            False,
                        "endCursor":
                            None,
                    },
                }
            },
        }
    )

    nodes = list(
        paginate_connection(
            client,
            "query Test {}",
            "productVariants",
            page_size=100,
            max_items=2,
        )
    )

    assert nodes == [
        {
            "id":
                "variant-1"
        },
        {
            "id":
                "variant-2"
        },
    ]

    assert len(
        client.calls
    ) == 1

    assert client.calls[0] == {
        "first": 2,
        "after": None,
    }


def test_stops_when_no_next_page(
) -> None:
    client = FakeClient(
        {
            None: {
                "productVariants": {
                    "nodes": [
                        {
                            "id":
                                "variant-1"
                        },
                    ],
                    "pageInfo": {
                        "hasNextPage":
                            False,
                        "endCursor":
                            None,
                    },
                }
            }
        }
    )

    nodes = list(
        paginate_connection(
            client,
            "query Test {}",
            "productVariants",
            page_size=100,
        )
    )

    assert nodes == [
        {
            "id":
                "variant-1"
        }
    ]

    assert len(
        client.calls
    ) == 1


def test_requires_cursor_for_next_page(
) -> None:
    client = FakeClient(
        {
            None: {
                "productVariants": {
                    "nodes": [
                        {
                            "id":
                                "variant-1"
                        },
                    ],
                    "pageInfo": {
                        "hasNextPage":
                            True,
                        "endCursor":
                            None,
                    },
                }
            }
        }
    )

    with pytest.raises(
        PaginationError,
        match="no endCursor",
    ):
        list(
            paginate_connection(
                client,
                "query Test {}",
                "productVariants",
            )
        )


def test_rejects_invalid_page_size(
) -> None:
    client = FakeClient({})

    with pytest.raises(
        ValueError,
        match="page_size",
    ):
        list(
            paginate_connection(
                client,
                "query Test {}",
                "productVariants",
                page_size=0,
            )
        )


def test_rejects_invalid_max_items(
) -> None:
    client = FakeClient({})

    with pytest.raises(
        ValueError,
        match="max_items",
    ):
        list(
            paginate_connection(
                client,
                "query Test {}",
                "productVariants",
                max_items=0,
            )
        )


def test_rejects_missing_connection(
) -> None:
    client = FakeClient(
        {
            None: {
                "somethingElse": {}
            }
        }
    )

    with pytest.raises(
        PaginationError,
        match="productVariants",
    ):
        list(
            paginate_connection(
                client,
                "query Test {}",
                "productVariants",
            )
        )