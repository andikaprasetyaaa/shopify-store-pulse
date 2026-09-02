from __future__ import annotations

from datetime import datetime, timezone

import scripts.sync_data as sync_data


def moment() -> datetime:
    return datetime(
        2026,
        9,
        1,
        14,
        37,
        22,
        512000,
        tzinfo=timezone.utc,
    )


def test_hour_bucket_rounds_down() -> None:
    assert sync_data.bucket_timestamp(
        moment(),
        "hour",
    ) == datetime(
        2026,
        9,
        1,
        14,
        0,
        tzinfo=timezone.utc,
    )


def test_day_bucket_rounds_down() -> None:
    assert sync_data.bucket_timestamp(
        moment(),
        "day",
    ) == datetime(
        2026,
        9,
        1,
        0,
        0,
        tzinfo=timezone.utc,
    )


def test_exact_bucket_is_unchanged() -> None:
    assert sync_data.bucket_timestamp(
        moment(),
        "exact",
    ) == moment()


def test_two_runs_in_one_hour_share_a_bucket() -> None:
    first = sync_data.bucket_timestamp(
        moment(),
        "hour",
    )

    second = sync_data.bucket_timestamp(
        moment().replace(minute=59),
        "hour",
    )

    assert first == second


def test_lock_blocks_a_second_run(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sync_data,
        "LOCK_PATH",
        tmp_path / "sync.lock",
    )

    assert sync_data.acquire_lock() is True
    assert sync_data.acquire_lock() is False

    sync_data.release_lock()

    assert sync_data.acquire_lock() is True

    sync_data.release_lock()


def test_stale_lock_is_reclaimed(
    tmp_path,
    monkeypatch,
) -> None:
    lock_path = tmp_path / "sync.lock"

    monkeypatch.setattr(
        sync_data,
        "LOCK_PATH",
        lock_path,
    )

    # PID that cannot be running.
    lock_path.write_text("999999")

    assert sync_data.acquire_lock() is True

    sync_data.release_lock()
