from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from storage.database import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_SERVING_PATH,
    StorageError,
    StorePulseDatabase,
    publish_serving_copy,
    resolve_read_path,
)

from tests.test_database import (
    make_inventory_catalog,
)


def build_database(
    database_path: Path,
    *,
    available: int,
) -> None:
    with StorePulseDatabase(
        database_path
    ) as database:
        database.save_inventory(
            make_inventory_catalog(
                available=available,
            ),
            snapshot_at=datetime(
                2026,
                9,
                1,
                8,
                0,
                tzinfo=timezone.utc,
            ),
        )

        database.checkpoint()


HOLD_WRITE_LOCK = """
import sys
import time

import duckdb

connection = duckdb.connect(sys.argv[1])
print("locked", flush=True)
time.sleep(30)
"""


def test_serving_copy_is_readable_while_writer_holds_lock(
    tmp_path: Path,
) -> None:
    """
    The whole point of the serving copy: a reader
    must succeed even while the sync holds the write
    lock on the live database.

    The writer runs in a separate process because
    DuckDB's cross-process file lock is what the API
    and the dashboard actually collide with.
    """

    source = tmp_path / "live.duckdb"
    target = tmp_path / "serving.duckdb"

    build_database(source, available=10)

    publish_serving_copy(source, target)

    writer = subprocess.Popen(
        [
            sys.executable,
            "-c",
            HOLD_WRITE_LOCK,
            str(source),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait until the lock is actually held.
        assert writer.stdout is not None

        deadline = time.time() + 30

        while time.time() < deadline:
            if writer.stdout.readline().strip() == (
                "locked"
            ):
                break

        else:
            pytest.fail(
                "writer never took the lock"
            )

        # The live database is locked out.
        with pytest.raises(
            duckdb.IOException
        ):
            duckdb.connect(
                str(source),
                read_only=True,
            )

        # The serving copy still reads fine.
        reader = duckdb.connect(
            str(target),
            read_only=True,
        )

        try:
            rows = reader.execute(
                """
                SELECT available
                FROM inventory_snapshots
                """
            ).fetchall()

        finally:
            reader.close()

    finally:
        writer.kill()
        writer.wait(timeout=30)

    assert rows == [(10,)]


def test_publish_replaces_previous_copy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "live.duckdb"
    target = tmp_path / "serving.duckdb"

    build_database(source, available=10)
    publish_serving_copy(source, target)

    build_database(source, available=3)
    publish_serving_copy(source, target)

    connection = duckdb.connect(
        str(target),
        read_only=True,
    )

    try:
        rows = connection.execute(
            """
            SELECT available
            FROM inventory_snapshots
            """
        ).fetchall()

    finally:
        connection.close()

    assert rows == [(3,)]


def test_publish_leaves_no_staging_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "live.duckdb"
    target = tmp_path / "serving.duckdb"

    build_database(source, available=10)
    publish_serving_copy(source, target)

    staging = target.with_name(
        target.name + ".tmp"
    )

    assert not staging.exists()


def test_publish_requires_a_source(
    tmp_path: Path,
) -> None:
    with pytest.raises(StorageError):
        publish_serving_copy(
            tmp_path / "missing.duckdb",
            tmp_path / "serving.duckdb",
        )


def test_readers_prefer_the_serving_copy(
    tmp_path: Path,
) -> None:
    live = tmp_path / DEFAULT_DATABASE_PATH
    serving = tmp_path / DEFAULT_SERVING_PATH

    build_database(live, available=10)

    # No serving copy yet -> fall back to live.
    assert resolve_read_path(
        tmp_path
    ) == live

    publish_serving_copy(live, serving)

    assert resolve_read_path(
        tmp_path
    ) == serving
