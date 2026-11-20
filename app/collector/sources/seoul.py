"""서울 열린데이터광장 — 시영주차장 실시간 주차대수 (GetParkingInfo).

http://openapi.seoul.go.kr:8088/{KEY}/json/GetParkingInfo/{start}/{end}/
- 한 번에 최대 1000행. 2026-11-20 기준 전체 122행.
- 좌표 필드 없음 → geom은 비워 두고 ADDR만 저장 (지오코딩은 마스터 통합 단계).
- PRK_STTS_YN == "1"인 곳만 실시간 연계 → 그때만 관측값 생성.
"""

import httpx

from app.collector.sources.base import LotRecord, Observation, SourceError, parse_kst, to_int

BASE_URL = "http://openapi.seoul.go.kr:8088"
SERVICE = "GetParkingInfo"
PAGE_SIZE = 1000
OK_CODE = "INFO-000"
NO_DATA_CODE = "INFO-200"

TYPE_NAMES = {"NS": "노상", "NW": "노외"}
SEOUL_MASTER_FIELDS = (
    "name",
    "realtime",
    "address",
    "total_spaces",
    "fee_basic",
    "fee_basic_min",
    "fee_add",
    "fee_add_min",
    "fee_day_max",
    "hours",
    "type",
)


class SeoulSource:
    name = "seoul"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def _url(self, start: int, end: int) -> str:
        return f"{BASE_URL}/{self.api_key}/json/{SERVICE}/{start}/{end}/"

    def fetch(self, client: httpx.Client) -> list[LotRecord]:
        rows: list[dict] = []
        start = 1
        while True:
            res = client.get(self._url(start, start + PAGE_SIZE - 1))
            res.raise_for_status()
            page_rows, total = parse_page(res.json())
            rows.extend(page_rows)
            start += PAGE_SIZE
            if not page_rows or start > total:
                break
        return [parse_row(r) for r in rows]


def parse_page(payload: dict) -> tuple[list[dict], int]:
    body = payload.get(SERVICE)
    if body is None:
        # 오류는 최상위 RESULT로 온다 (예: 인증키 오류)
        result = payload.get("RESULT", {})
        if result.get("CODE") == NO_DATA_CODE:
            return [], 0
        raise SourceError(f"seoul: {result.get('CODE')} {result.get('MESSAGE')}")
    result = body.get("RESULT", {})
    if result.get("CODE") != OK_CODE:
        raise SourceError(f"seoul: {result.get('CODE')} {result.get('MESSAGE')}")
    return body.get("row", []), int(body.get("list_total_count", 0))


def parse_row(row: dict) -> LotRecord:
    total = to_int(row.get("TPKCT"))
    occupied = to_int(row.get("NOW_PRK_VHCL_CNT"))
    provided_at = parse_kst(row.get("NOW_PRK_VHCL_UPDT_TM"))
    realtime = str(row.get("PRK_STTS_YN", "")).strip() == "1"

    observation = None
    if realtime and provided_at is not None and total is not None and occupied is not None:
        observation = Observation(
            provided_at=provided_at,
            # 주차 대수가 총면수를 넘는 경우가 있어 잔여면수는 0 아래로 내리지 않는다
            available_spaces=max(total - occupied, 0),
            occupied=occupied,
            total_spaces=total,
        )

    pklt_type = str(row.get("PKLT_TYPE", "")).strip()
    return LotRecord(
        source="seoul",
        source_id=str(row["PKLT_CD"]).strip(),
        name=str(row.get("PKLT_NM", "")).strip(),
        realtime=realtime,
        address=(str(row.get("ADDR", "")).strip() or None),
        total_spaces=total,
        fee_basic=to_int(row.get("BSC_PRK_CRG")),
        fee_basic_min=to_int(row.get("BSC_PRK_HR")),
        fee_add=to_int(row.get("ADD_PRK_CRG")),
        fee_add_min=to_int(row.get("ADD_PRK_HR")),
        fee_day_max=to_int(row.get("DAY_MAX_CRG")),
        hours={
            "weekday": [row.get("WD_OPER_BGNG_TM"), row.get("WD_OPER_END_TM")],
            "weekend": [row.get("WE_OPER_BGNG_TM"), row.get("WE_OPER_END_TM")],
            "holiday": [row.get("LHLDY_OPER_BGNG_TM"), row.get("LHLDY_OPER_END_TM")],
        },
        type=TYPE_NAMES.get(pklt_type) or (str(row.get("PRK_TYPE_NM", "")).strip() or None),
        observation=observation,
        master_fields=SEOUL_MASTER_FIELDS,
    )
