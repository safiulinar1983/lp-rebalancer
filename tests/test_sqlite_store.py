import sqlite3

import pytest

from storage.sqlite_store import SQLiteStore


def test_creates_schema_and_records_version(tmp_path):
    db_path = tmp_path / "test.db"
    SQLiteStore(db_path)

    with sqlite3.connect(db_path) as db:
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "schema_version",
            "events",
            "decisions",
            "wrong",
            "to_learn",
        } <= tables

        assert db.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0] == 1


def test_records_and_reads_event(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")
    event_id = store.record_event(
        "pool_state",
        {"tick": 219103, "network": "base_sepolia"},
    )

    events = store.list_events()

    assert events[0]["id"] == event_id
    assert events[0]["event_type"] == "pool_state"
    assert events[0]["payload"]["tick"] == 219103


def test_records_decision_wrong_and_learning_candidate(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")

    decision_id = store.record_decision(
        "OUT_OF_RANGE",
        {"tick": 219250},
    )
    wrong_id = store.record_wrong(
        "rpc_error",
        {"message": "temporary failure"},
    )
    learning_id = store.add_candidate(
        {"state": "OUT_OF_RANGE", "reviewed": False},
    )

    assert decision_id > 0
    assert wrong_id > 0
    assert learning_id > 0

    store.update_wrong_status(wrong_id, "investigating")

    with sqlite3.connect(tmp_path / "test.db") as db:
        status = db.execute(
            "SELECT status FROM wrong WHERE id = ?", (wrong_id,)
        ).fetchone()[0]
        assert status == "investigating"


def test_rejects_invalid_wrong_status(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")
    case_id = store.record_wrong("test", {})

    with pytest.raises(ValueError):
        store.update_wrong_status(case_id, "unknown")


def test_rejects_empty_event_type(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")

    with pytest.raises(ValueError):
        store.record_event(" ", {})


def test_events_survive_store_recreation(tmp_path):
    db_path = tmp_path / "test.db"
    SQLiteStore(db_path).record_event("startup", {"ok": True})

    events = SQLiteStore(db_path).list_events()

    assert len(events) == 1
    assert events[0]["payload"]["ok"] is True


def test_decision_is_also_recorded_as_event(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")

    decision_id = store.record_decision(
        "OUT_OF_RANGE",
        {"tick": 219250, "network": "base_sepolia"},
    )

    events = store.list_events()

    assert len(events) == 1
    assert events[0]["event_type"] == "decision"
    assert events[0]["payload"]["decision_id"] == decision_id
    assert events[0]["payload"]["decision"] == "OUT_OF_RANGE"
    assert events[0]["payload"]["payload"]["tick"] == 219250


def test_wrong_case_is_also_recorded_as_event(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")

    wrong_id = store.record_wrong(
        "rpc_error",
        {"message": "temporary failure"},
    )

    events = store.list_events()

    assert len(events) == 1
    assert events[0]["event_type"] == "wrong"
    assert events[0]["payload"]["wrong_id"] == wrong_id
    assert events[0]["payload"]["category"] == "rpc_error"
    assert events[0]["payload"]["payload"]["message"] == "temporary failure"


def test_lists_decisions_newest_first(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")

    first_id = store.record_decision("IN_RANGE", {"tick": 219103})
    second_id = store.record_decision("OUT_OF_RANGE", {"tick": 219250})

    decisions = store.list_decisions()

    assert [item["id"] for item in decisions] == [second_id, first_id]
    assert decisions[0]["decision"] == "OUT_OF_RANGE"
    assert decisions[0]["payload"]["tick"] == 219250


def test_list_decisions_respects_limit(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")

    store.record_decision("IN_RANGE", {"tick": 219100})
    store.record_decision("OUT_OF_RANGE", {"tick": 219250})

    decisions = store.list_decisions(limit=1)

    assert len(decisions) == 1
    assert decisions[0]["decision"] == "OUT_OF_RANGE"


def test_list_decisions_rejects_invalid_limit(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")

    with pytest.raises(ValueError):
        store.list_decisions(limit=0)


def test_monitor_snapshot_and_decision_are_persisted(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")
    snapshot = {
        "network": "base_sepolia",
        "pool_address": "0x123",
        "token_id": 82740,
        "current_tick": 219103,
        "lower_tick": 219000,
        "upper_tick": 219200,
        "fees_value_usd": "0.12",
        "decision": "IN_RANGE",
    }

    store.record_event("monitor_snapshot", snapshot)
    decision_id = store.record_decision("IN_RANGE", snapshot)

    events = store.list_events()
    decisions = store.list_decisions()

    assert events[0]["event_type"] == "decision"
    assert events[1]["event_type"] == "monitor_snapshot"
    assert events[1]["payload"]["token_id"] == 82740
    assert events[1]["payload"]["current_tick"] == 219103
    assert decisions[0]["id"] == decision_id
    assert decisions[0]["payload"]["network"] == "base_sepolia"
