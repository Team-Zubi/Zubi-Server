from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

import httpx

KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class Observation:
    """출처가 알려 준 한 시점의 실시간 값."""

    provided_at: datetime
    available_spaces: int
    occupied: int | None
    total_spaces: int | None


@dataclass(frozen=True)
class LotRecord:
    """출처 한 행을 정규화한 결과. 마스터 필드 + (있으면) 실시간 관측값."""

    source: str
    source_id: str
    name: str
    realtime: bool
    region: str | None = None
    address: str | None = None
    total_spaces: int | None = None
    fee_basic: int | None = None
    fee_basic_min: int | None = None
    fee_add: int | None = None
    fee_add_min: int | None = None
    fee_day_max: int | None = None
    hours: dict | None = None
    type: str | None = None
    observation: Observation | None = None
    # 마스터 upsert 때 갱신할 필드 (출처가 주지 않는 값으로 기존 값을 지우지 않도록)
    master_fields: tuple[str, ...] = field(default=("name", "realtime", "total_spaces"))


class Source(Protocol):
    name: str

    def fetch(self, client: httpx.Client) -> list[LotRecord]: ...


class SourceError(RuntimeError):
    """출처 응답이 오류이거나 형식이 예상과 다를 때."""


def parse_kst(value: str | None) -> datetime | None:
    """'2026-11-20 09:37:23' / '2026-11-20 09:37:00.155' → KST aware datetime."""
    if not value or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    return None


def to_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None
