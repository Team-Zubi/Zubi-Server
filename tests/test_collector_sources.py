import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from app.collector.sources import GyeonggiSource, SeoulSource, SourceError
from app.collector.sources.base import KST, parse_kst
from app.collector.sources.gg import parse_response
from app.collector.sources.seoul import parse_page, parse_row

FIXTURES = Path(__file__).parent / "fixtures"


def seoul_payload() -> dict:
    return json.loads((FIXTURES / "seoul_GetParkingInfo.json").read_text(encoding="utf-8"))


def gg_payload() -> bytes:
    return (FIXTURES / "gg_availability.xml").read_bytes()


def test_parse_kst() -> None:
    assert parse_kst("2026-11-20 09:37:23") == datetime(2026, 11, 20, 9, 37, 23, tzinfo=KST)
    assert parse_kst("2026-11-20 09:37:00.155").microsecond == 155000
    assert parse_kst("") is None
    assert parse_kst("not a date") is None


def test_seoul_realtime_row() -> None:
    rows, total = parse_page(seoul_payload())
    assert total == 3
    rec = parse_row(rows[0])
    assert rec.source == "seoul"
    assert rec.source_id == "171721"
    assert rec.realtime is True
    assert rec.type == "노외"
    assert rec.fee_basic == 430 and rec.fee_basic_min == 5
    assert rec.hours["weekday"] == ["0000", "2400"]
    assert rec.observation is not None
    assert rec.observation.total_spaces == 1260
    assert rec.observation.occupied == 533
    assert rec.observation.available_spaces == 1260 - 533
    assert rec.observation.provided_at.tzinfo == KST


def test_seoul_non_realtime_row_has_no_observation() -> None:
    rows, _ = parse_page(seoul_payload())
    rec = parse_row(rows[2])
    assert rec.realtime is False
    assert rec.observation is None
    assert "geom" not in rec.master_fields  # 수집기는 좌표를 건드리지 않음


def test_seoul_over_capacity_clamps_available() -> None:
    row = dict(seoul_payload()["GetParkingInfo"]["row"][0], TPKCT=10.0, NOW_PRK_VHCL_CNT=12.0)
    obs = parse_row(row).observation
    assert obs.available_spaces == 0
    assert obs.occupied == 12


def test_seoul_error_result() -> None:
    with pytest.raises(SourceError, match="INFO-100"):
        parse_page({"RESULT": {"CODE": "INFO-100", "MESSAGE": "인증키가 유효하지 않습니다."}})
    assert parse_page({"RESULT": {"CODE": "INFO-200", "MESSAGE": "데이터 없음"}}) == ([], 0)


def test_seoul_fetch_paginates() -> None:
    payload = seoul_payload()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        records = SeoulSource("KEY").fetch(client)
    assert len(records) == 3
    assert calls == ["/KEY/json/GetParkingInfo/1/1000/"]


def test_gg_parse() -> None:
    records = parse_response(gg_payload())
    assert len(records) == 3
    # 같은 pkplcId(00014)가 시·군마다 있으므로 laeId를 붙여 구분
    assert records[0].source_id == "31050-00014"
    assert records[1].source_id == "31020-00014"
    assert records[1].region == "성남시"
    obs = records[1].observation
    assert obs.total_spaces == 210
    assert obs.available_spaces == 22
    assert obs.occupied == 188
    assert obs.provided_at == datetime(2026, 11, 20, 9, 37, 9, tzinfo=KST)


def test_gg_error_and_empty() -> None:
    err = (
        '<?xml version="1.0" encoding="UTF-8"?><ServiceResult><msgHeader>'
        "<headerCd>6</headerCd><headerMsg>등록되지 않은 키 입니다.</headerMsg>"
        "</msgHeader></ServiceResult>"
    ).encode()
    with pytest.raises(SourceError, match="gg: 6"):
        parse_response(err)
    empty = err.replace(b"<headerCd>6</headerCd>", b"<headerCd>4</headerCd>")
    assert parse_response(empty) == []
    with pytest.raises(SourceError):
        parse_response(b"<html>not xml")


def test_gg_fetch_sends_key_param() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["serviceKey"] == "KEY"
        return httpx.Response(200, content=gg_payload())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert len(GyeonggiSource("KEY").fetch(client)) == 3
