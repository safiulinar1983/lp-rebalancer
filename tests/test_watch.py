"""Tests for the foreground watcher in ``scripts/watch.py``.

The watcher must be testable without an RPC endpoint: its loop and lock are
independent from the configuration and the blockchain adapters.
"""

import logging
import os
import threading
from dataclasses import replace

import pytest

from config import MODE_LIVE, load_config
from rebalance_cycle import CycleResult
from scripts.watch import (
    AlreadyRunningError,
    FatalWatchError,
    SingleInstanceLock,
    backoff_delay,
    configure_logging,
    next_config,
    parse_args,
    run_forever,
)


class FakeStopEvent:
    """Stop after a fixed number of ``wait`` calls."""

    def __init__(self, waits: int):
        self.waits = waits
        self.wait_calls = 0

    def is_set(self) -> bool:
        return False

    def wait(self, timeout: int) -> bool:
        self.wait_calls += 1
        return self.wait_calls >= self.waits


def _logger() -> logging.Logger:
    logger = logging.getLogger("tests.watch")
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False
    return logger


def test_parse_args_defaults_come_from_config():
    args = parse_args([])

    assert args.interval is None
    assert args.once is False
    assert args.dry_run is False
    assert args.max_backoff == 300


def test_parse_args_accepts_interval_and_flags():
    args = parse_args(["--interval", "60", "--once", "--dry-run"])

    assert args.interval == 60
    assert args.once is True
    assert args.dry_run is True


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_parse_args_rejects_invalid_intervals(value):
    with pytest.raises(SystemExit):
        parse_args(["--interval", value])


def test_single_instance_lock_blocks_a_second_holder(tmp_path):
    path = tmp_path / "data" / "watch.lock"
    first = SingleInstanceLock(path)
    first.acquire()

    try:
        second = SingleInstanceLock(path)

        with pytest.raises(AlreadyRunningError, match="another watch process"):
            second.acquire()
    finally:
        first.release()

    assert str(os.getpid()) in path.read_text(encoding="utf-8")


def test_single_instance_lock_can_be_reacquired(tmp_path):
    path = tmp_path / "watch.lock"

    with SingleInstanceLock(path):
        pass

    with SingleInstanceLock(path) as lock:
        assert lock.path == path


@pytest.mark.parametrize(
    ("failures", "expected"),
    [(1, 5), (2, 10), (3, 20), (4, 40), (20, 300)],
)
def test_backoff_delay_doubles_and_is_capped(failures, expected):
    assert backoff_delay(failures, interval=5, max_backoff=300) == expected


def test_backoff_delay_rejects_zero_failures():
    with pytest.raises(ValueError, match="failures must be positive"):
        backoff_delay(0, interval=5, max_backoff=300)


def test_run_forever_once_returns_after_one_cycle():
    calls = []

    def run_once():
        calls.append(1)
        return CycleResult(mode="DRY_RUN", action="HOLD")

    result = run_forever(
        run_once,
        interval=5,
        stop_event=threading.Event(),
        logger=_logger(),
        once=True,
    )

    assert result == 0
    assert len(calls) == 1


def test_run_forever_once_returns_error_on_failure():
    def run_once():
        raise RuntimeError("rpc unavailable")

    result = run_forever(
        run_once,
        interval=5,
        stop_event=threading.Event(),
        logger=_logger(),
        once=True,
    )

    assert result == 1


def test_run_forever_retries_after_a_transient_failure():
    calls = []

    def run_once():
        calls.append(1)

        if len(calls) == 1:
            raise RuntimeError("rpc unavailable")

        return CycleResult(mode="DRY_RUN", action="HOLD")

    stop_event = FakeStopEvent(waits=2)

    result = run_forever(
        run_once,
        interval=5,
        stop_event=stop_event,
        logger=_logger(),
    )

    assert result == 0
    assert len(calls) == 2


def test_run_forever_stops_immediately_when_event_is_set():
    stop_event = threading.Event()
    stop_event.set()
    calls = []

    result = run_forever(
        lambda: calls.append(1) or CycleResult(mode="DRY_RUN", action="HOLD"),
        interval=5,
        stop_event=stop_event,
        logger=_logger(),
    )

    assert result == 0
    assert calls == []


def test_next_config_follows_a_new_live_position():
    config = replace(
        load_config(),
        mode=MODE_LIVE,
        position_token_id=83054,
    )
    result = CycleResult(
        mode=MODE_LIVE,
        action="REBALANCE",
        new_token_id=83055,
    )

    updated = next_config(config, result, _logger())

    assert updated.position_token_id == 83055
    assert config.position_token_id == 83054


def test_next_config_keeps_the_position_after_a_blocked_rebalance():
    config = replace(
        load_config(),
        mode=MODE_LIVE,
        position_token_id=83054,
    )
    result = CycleResult(
        mode=MODE_LIVE,
        action="REBALANCE",
        blocked_reason="gas budget",
    )

    assert next_config(config, result, _logger()) is config


def test_next_config_does_not_move_a_dry_run_position():
    config = replace(
        load_config(),
        mode="DRY_RUN",
        position_token_id=83054,
    )
    result = CycleResult(
        mode="DRY_RUN",
        action="REBALANCE",
        new_token_id=83055,
    )

    assert next_config(config, result, _logger()) is config


def test_next_config_fails_when_the_new_position_is_unknown():
    config = replace(
        load_config(),
        mode=MODE_LIVE,
        position_token_id=83054,
    )
    result = CycleResult(mode=MODE_LIVE, action="REBALANCE")

    with pytest.raises(FatalWatchError, match="new LP NFT id"):
        next_config(config, result, _logger())


def test_run_forever_stops_on_a_fatal_error():
    def run_once():
        raise FatalWatchError("position changed unexpectedly")

    result = run_forever(
        run_once,
        interval=5,
        stop_event=FakeStopEvent(waits=100),
        logger=_logger(),
    )

    assert result == 1


def test_run_forever_stops_on_an_unsafe_transaction():
    from blockchain.tx import ChainReorganizationError

    def run_once():
        raise ChainReorganizationError("receipt left the canonical chain")

    result = run_forever(
        run_once,
        interval=5,
        stop_event=FakeStopEvent(waits=100),
        logger=_logger(),
    )

    assert result == 1


def test_configure_logging_writes_to_a_rotating_file(tmp_path):
    log_path = tmp_path / "logs" / "watch.log"
    logger = configure_logging(log_path)

    try:
        logger.info("watcher test message")
        logger.handlers[0].flush()
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    text = log_path.read_text(encoding="utf-8")
    assert "watcher test message" in text
    assert "INFO" in text
