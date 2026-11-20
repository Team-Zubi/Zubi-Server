"""경기도 교통정보센터 — 주차장 가용정보 (getParkingPlaceAvailabilityInfoList).

https://openapigits.gg.go.kr/api/rest/getParkingPlaceAvailabilityInfoList?serviceKey=KEY
- XML 응답, 한 번에 전체 (2026-11-20 기준 818행, 17개 시·군).
- pkplcId는 시·군(laeId) 안에서만 고유 → source_id = "{laeId}-{pkplcId}".
- 요금·위치는 이 API에 없음 (경기데이터드림 표준데이터와 조인은 마스터 통합 단계).
"""

import xml.etree.ElementTree as ET

import httpx

from app.collector.sources.base import LotRecord, Observation, SourceError, parse_kst, to_int

URL = "https://openapigits.gg.go.kr/api/rest/getParkingPlaceAvailabilityInfoList"
OK_CODE = "0"
NO_DATA_CODE = "4"
GG_MASTER_FIELDS = ("name", "realtime", "region", "total_spaces")


class GyeonggiSource:
    name = "gg"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def fetch(self, client: httpx.Client) -> list[LotRecord]:
        res = client.get(URL, params={"serviceKey": self.api_key})
        res.raise_for_status()
        return parse_response(res.content)


def _text(el: ET.Element, tag: str) -> str:
    return (el.findtext(tag) or "").strip()


def parse_response(content: bytes) -> list[LotRecord]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise SourceError(f"gg: XML 파싱 실패 ({e})") from e

    code = (root.findtext("msgHeader/headerCd") or "").strip()
    if code == NO_DATA_CODE:
        return []
    if code != OK_CODE:
        raise SourceError(f"gg: {code} {root.findtext('msgHeader/headerMsg')}")

    return [parse_item(item) for item in root.iter("itemList")]


def parse_item(item: ET.Element) -> LotRecord:
    total = to_int(_text(item, "pklotCnt"))
    available = to_int(_text(item, "avblPklotCnt"))
    provided_at = parse_kst(_text(item, "ocrnDt"))

    observation = None
    if provided_at is not None and available is not None:
        available = max(available, 0)
        observation = Observation(
            provided_at=provided_at,
            available_spaces=available,
            occupied=(max(total - available, 0) if total is not None else None),
            total_spaces=total,
        )

    return LotRecord(
        source="gg",
        source_id=f"{_text(item, 'laeId')}-{_text(item, 'pkplcId')}",
        name=_text(item, "pkplcNm"),
        realtime=True,
        region=_text(item, "laeNm") or None,
        total_spaces=total,
        observation=observation,
        master_fields=GG_MASTER_FIELDS,
    )
