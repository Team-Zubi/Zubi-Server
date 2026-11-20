import logging
from contextlib import contextmanager

import httpx

from app.collector import runner
from app.collector.log import RedactingFormatter
from app.collector.sources.base import LotRecord
from app.collector.store import StoreResult


class FakeSession:
    @contextmanager
    def begin(self):
        yield

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class OkSource:
    name = "ok"

    def fetch(self, client: httpx.Client) -> list[LotRecord]:
        return [LotRecord(source="ok", source_id="1", name="a", realtime=True)]


class BrokenSource:
    name = "broken"

    def fetch(self, client: httpx.Client) -> list[LotRecord]:
        raise httpx.ConnectError("boom")


def test_one_failing_source_does_not_block_others(monkeypatch) -> None:
    monkeypatch.setattr(runner, "store", lambda session, records, at: StoreResult(1, 1, 1))
    with httpx.Client() as client:
        runs = runner.collect_once([BrokenSource(), OkSource()], client, FakeSession)
    assert [(r.source, r.ok) for r in runs] == [("broken", False), ("ok", True)]
    assert runs[1].result.snapshots_inserted == 1


def test_redacting_formatter_hides_keys() -> None:
    fmt = RedactingFormatter("%(message)s", ["SECRETKEY", ""])
    record = logging.LogRecord(
        "x", logging.ERROR, __file__, 1, "GET http://h/SECRETKEY/json", None, None
    )
    assert fmt.format(record) == "GET http://h/***/json"
