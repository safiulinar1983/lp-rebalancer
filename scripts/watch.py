"""Run the rebalancing cycle continuously as a foreground watcher.

The watcher is deliberately thin: it does not contain strategy or blockchain
logic, it only runs the same cycle as ``scripts/rebalance.py`` on an interval.
``strategy.check_interval`` is the default period; ``--interval`` overrides it.

Safety features:

* a platform file lock prevents two watchers from managing the same wallet;
* transient RPC failures are retried with exponential backoff;
* ``--once`` runs exactly one cycle (handy for Task Scheduler or cron);
* ``--dry-run`` forces ``DRY_RUN`` even when ``config.yaml`` says ``LIVE``;
* logs go to ``data/watch.log`` with rotation and to the console.

Run it in the foreground and stop it with Ctrl+C::

    python scripts/watch.py
    python scripts/watch.py --once --dry-run
    python scripts/watch.py --interval 60
"""

import argparse
import logging
import os
import signal
import sys
import threading
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

if __package__ in (None, ""):  # allow `python scripts/watch.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blockchain.rpc import connect, safe_rpc_url
from blockchain.tx import UnsafeTransactionError
from config import MODE_DRY_RUN, MODE_LIVE, AppConfig, load_config
from rebalance_cycle import CycleResult, format_cycle_result
from scripts._common import PROJECT_ROOT
from scripts.rebalance import build_account, run_cycle
from storage.sqlite_store import SQLiteStore

DEFAULT_LOG_FILE = PROJECT_ROOT / "data" / "watch.log"
DEFAULT_LOCK_FILE = PROJECT_ROOT / "data" / "watch.lock"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "lp_rebalancer.db"
DEFAULT_MAX_BACKOFF_SECONDS = 300

LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 5
LOGGER_NAME = "lp_rebalancer.watch"


class AlreadyRunningError(RuntimeError):
    """Raised when another watcher holds the instance lock."""


class FatalWatchError(RuntimeError):
    """Raised when continuing could manage the wrong LP position."""


class SingleInstanceLock:
    """Advisory file lock that dies with the process.

    The file is left on disk after a clean exit, but the OS releases the lock
    when the process ends, so a stale file does not prevent a restart.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._handle = None

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()

    def acquire(self) -> None:
        if self._handle is not None:
            raise RuntimeError("lock is already held by this instance")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        handle = os.fdopen(descriptor, "r+", encoding="utf-8")

        try:
            # msvcrt cannot lock a zero-length file, so make sure byte 0 exists
            # before taking the lock.
            handle.seek(0, os.SEEK_END)

            if handle.tell() == 0:
                handle.write("\n")
                handle.flush()

            handle.seek(0)
            _lock_file(handle)
        except OSError as exc:
            handle.close()
            raise AlreadyRunningError(
                f"another watch process holds the lock {self.path}"
            ) from exc

        self._handle = handle
        # Keep the holder's pid in the file for operators. Truncation is
        # unnecessary and can be racy on Windows, so only overwrite the prefix.
        handle.seek(0)
        handle.write(f"{os.getpid()}\n")
        handle.flush()

    def release(self) -> None:
        handle = self._handle

        if handle is None:
            return

        self._handle = None

        try:
            _unlock_file(handle)
        finally:
            handle.close()


def _lock_file(handle) -> None:
    """Take a non-blocking exclusive lock on ``handle``."""
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle) -> None:
    """Release the lock taken by :func:`_lock_file`."""
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def positive_int(value: str) -> int:
    """Argparse type for a strictly positive integer."""
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc

    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")

    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the LP rebalancing cycle continuously. "
            "The default period is strategy.check_interval from config.yaml."
        ),
    )
    parser.add_argument(
        "--interval",
        type=positive_int,
        default=None,
        help="seconds between cycles (overrides strategy.check_interval)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="run one cycle and exit; useful for Task Scheduler or cron",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="force DRY_RUN even when config.yaml sets mode: LIVE",
    )
    parser.add_argument(
        "--max-backoff",
        type=positive_int,
        default=DEFAULT_MAX_BACKOFF_SECONDS,
        help="maximum delay after consecutive failures, in seconds",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG_FILE,
        help=f"rotating log file (default: {DEFAULT_LOG_FILE})",
    )
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=DEFAULT_LOCK_FILE,
        help=f"single-instance lock file (default: {DEFAULT_LOCK_FILE})",
    )
    return parser.parse_args(argv)


def configure_logging(log_file: str | Path) -> logging.Logger:
    """Configure the watcher logger with rotating file and console output."""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # pythonw.exe (Task Scheduler) has no stderr; file logging still works.
    if sys.stderr is not None:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def backoff_delay(
    failures: int,
    interval: int,
    max_backoff: int,
) -> int:
    """Return the delay after ``failures`` consecutive failed cycles."""
    if failures < 1:
        raise ValueError("failures must be positive")

    # Cap the exponent so a long outage cannot build an enormous integer.
    exponent = min(failures - 1, 10)
    return min(interval * (2**exponent), max_backoff)


def next_config(
    config: AppConfig,
    result: CycleResult,
    logger: logging.Logger,
) -> AppConfig:
    """Follow a newly minted NFT and stop when its id cannot be determined.

    A LIVE rebalance closes the configured NFT and mints a new one. Without
    this hand-off the next cycle would keep reading the emptied NFT and could
    try to close it again.
    """
    if config.mode != MODE_LIVE or result.action != "REBALANCE":
        return config

    if result.blocked:
        return config

    if result.new_token_id is None:
        raise FatalWatchError(
            "rebalance completed but the new LP NFT id could not be determined; "
            "set position_manager.token_id in config.yaml and restart"
        )

    if result.new_token_id == config.position_token_id:
        return config

    logger.info(
        "active LP NFT switched from #%s to #%s",
        config.position_token_id,
        result.new_token_id,
    )

    return replace(config, position_token_id=result.new_token_id)


def result_fingerprint(result: CycleResult) -> tuple:
    """Return the parts of a cycle result that make a report worth repeating."""
    return (
        result.action,
        tuple((step.name, step.status) for step in result.steps),
        result.blocked_reason,
        result.new_token_id,
    )


def log_cycle_result(
    result: CycleResult,
    logger: logging.Logger,
    previous_fingerprint: tuple | None,
) -> tuple:
    """Log a concise line every cycle and a full report when it changes."""
    fingerprint = result_fingerprint(result)

    logger.info(
        "cycle mode=%s action=%s steps=%d sent=%d%s%s",
        result.mode,
        result.action,
        len(result.steps),
        len(result.sent_steps),
        f" new_token_id={result.new_token_id}"
        if result.new_token_id is not None
        else "",
        f" blocked={result.blocked_reason}" if result.blocked else "",
    )

    if fingerprint != previous_fingerprint:
        logger.info("\n%s", format_cycle_result(result))

    return fingerprint


def run_forever(
    run_once: Callable[[], CycleResult],
    *,
    interval: int,
    stop_event: threading.Event,
    logger: logging.Logger,
    max_backoff: int = DEFAULT_MAX_BACKOFF_SECONDS,
    once: bool = False,
) -> int:
    """Run cycles until ``stop_event`` is set.

    Returns ``0`` when stopped normally and ``1`` when ``--once`` encountered
    an error. In continuous mode errors are logged and retried; the process
    keeps running.
    """
    failures = 0
    previous_fingerprint = None

    while not stop_event.is_set():
        try:
            result = run_once()
        except (FatalWatchError, UnsafeTransactionError):
            # A reorg or an unconfirmed transaction has an unknown outcome:
            # retrying the whole cycle could duplicate on-chain actions.
            logger.exception("fatal cycle error; stopping the watcher")
            return 1
        except Exception:
            failures += 1
            delay = backoff_delay(failures, interval, max_backoff)
            logger.exception(
                "cycle failed (consecutive failure %d); retrying in %ss",
                failures,
                delay,
            )

            if once:
                return 1

            if stop_event.wait(delay):
                break

            continue

        failures = 0
        previous_fingerprint = log_cycle_result(
            result,
            logger,
            previous_fingerprint,
        )

        if once:
            return 0

        if stop_event.wait(interval):
            break

    return 0


def install_signal_handlers(
    stop_event: threading.Event,
    logger: logging.Logger,
) -> None:
    """Stop after the current cycle on SIGINT/SIGTERM/SIGBREAK."""

    def handler(signum, _frame) -> None:
        logger.info(
            "received signal %s; stopping after the current cycle",
            signum,
        )
        stop_event.set()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        signum = getattr(signal, name, None)

        if signum is None:
            continue

        try:
            signal.signal(signum, handler)
        except (OSError, ValueError):
            # Signal handlers are not available in every embedding context.
            continue


def _run(
    config: AppConfig,
    *,
    interval: int,
    max_backoff: int,
    once: bool,
    stop_event: threading.Event,
    logger: logging.Logger,
) -> int:
    """Connect, build one cycle factory and hand control to the loop."""
    logger.info(
        "watch starting network=%s chain_id=%s dex=%s mode=%s token_id=%s "
        "rpc=%s interval=%ss",
        config.network,
        config.expected_chain_id,
        config.dex,
        config.mode,
        config.position_token_id,
        safe_rpc_url(config.rpc_url),
        interval,
    )

    w3 = connect(config.rpc_url, expected_chain_id=config.expected_chain_id)
    account = build_account(w3, config)
    store = SQLiteStore(DEFAULT_DB_PATH)
    active_config = config

    def run_once() -> CycleResult:
        nonlocal active_config

        result = run_cycle(
            w3,
            active_config,
            account=account,
            store=store,
        )
        active_config = next_config(active_config, result, logger)
        return result

    return run_forever(
        run_once,
        interval=interval,
        stop_event=stop_event,
        logger=logger,
        max_backoff=max_backoff,
        once=once,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logger = configure_logging(args.log_file)

    try:
        config = load_config()
    except Exception:
        logger.exception("could not load configuration")
        return 1

    if args.dry_run and config.mode != MODE_DRY_RUN:
        logger.info(
            "overriding strategy.mode=%s with DRY_RUN",
            config.mode,
        )
        config = replace(config, mode=MODE_DRY_RUN)

    interval = (
        args.interval if args.interval is not None else config.check_interval
    )
    max_backoff = max(args.max_backoff, interval)

    lock = SingleInstanceLock(args.lock_file)

    try:
        lock.acquire()
    except AlreadyRunningError as exc:
        logger.error("%s", exc)
        return 2

    stop_event = threading.Event()
    install_signal_handlers(stop_event, logger)

    try:
        return _run(
            config,
            interval=interval,
            max_backoff=max_backoff,
            once=args.once,
            stop_event=stop_event,
            logger=logger,
        )
    except KeyboardInterrupt:
        stop_event.set()
        logger.info("interrupted")
        return 0
    except Exception:
        logger.exception("watch failed")
        return 1
    finally:
        lock.release()
        logger.info("watch stopped")


if __name__ == "__main__":
    sys.exit(main())


