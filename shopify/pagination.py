from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Protocol


class QueryClient(Protocol):
    def query(
        self,
        document: str,
        variables: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


class PaginationError(RuntimeError):
    pass


def paginate_connection(
    client: QueryClient,
    document: str,
    connection_name: str,
    *,
    variables: Mapping[str, Any] | None = None,
    page_size: int = 100,
    max_items: int | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Iterate through a Shopify GraphQL cursor connection.

    Required GraphQL variables:
        $first
        $after

    Required connection fields:
        nodes
        pageInfo {
            hasNextPage
            endCursor
        }

    max_items:
        None -> collect all available nodes
        N    -> stop after N nodes
    """

    if not 1 <= page_size <= 250:
        raise ValueError(
            "page_size must be between 1 and 250"
        )

    if max_items is not None and max_items < 1:
        raise ValueError(
            "max_items must be at least 1 or None"
        )

    cursor: str | None = None
    seen_cursors: set[str] = set()
    yielded_count = 0

    while True:
        request_variables = dict(
            variables or {}
        )

        request_page_size = page_size

        if max_items is not None:
            remaining = (
                max_items - yielded_count
            )

            if remaining <= 0:
                return

            request_page_size = min(
                page_size,
                remaining,
            )

        request_variables["first"] = (
            request_page_size
        )

        request_variables["after"] = cursor

        data = client.query(
            document,
            request_variables,
        )

        connection = data.get(
            connection_name
        )

        if not isinstance(
            connection,
            dict,
        ):
            raise PaginationError(
                "GraphQL response is missing "
                f"connection '{connection_name}'."
            )

        nodes = connection.get(
            "nodes"
        )

        if not isinstance(
            nodes,
            list,
        ):
            raise PaginationError(
                f"Connection '{connection_name}' "
                "does not contain a nodes list."
            )

        for node in nodes:
            if not isinstance(
                node,
                dict,
            ):
                raise PaginationError(
                    f"Connection '{connection_name}' "
                    "returned a non-object node."
                )

            yield node
            yielded_count += 1

            if (
                max_items is not None
                and yielded_count >= max_items
            ):
                return

        page_info = connection.get(
            "pageInfo"
        )

        if not isinstance(
            page_info,
            dict,
        ):
            raise PaginationError(
                f"Connection '{connection_name}' "
                "does not contain pageInfo."
            )

        has_next_page = page_info.get(
            "hasNextPage"
        )

        if not isinstance(
            has_next_page,
            bool,
        ):
            raise PaginationError(
                f"Connection '{connection_name}' "
                "has invalid hasNextPage."
            )

        if not has_next_page:
            return

        end_cursor = page_info.get(
            "endCursor"
        )

        if (
            not isinstance(
                end_cursor,
                str,
            )
            or not end_cursor
        ):
            raise PaginationError(
                f"Connection '{connection_name}' "
                "says another page exists "
                "but has no endCursor."
            )

        if end_cursor in seen_cursors:
            raise PaginationError(
                f"Connection '{connection_name}' "
                f"repeated cursor '{end_cursor}'."
            )

        seen_cursors.add(
            end_cursor
        )

        cursor = end_cursor