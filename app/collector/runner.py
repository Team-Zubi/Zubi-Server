"""수집 주기 실행. 출처마다 따로 호출·저장해서 한 출처 장애가 다른 출처를 막지 않게 한다."""

import logging
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.collector.sources import GyeonggiSource, SeoulSource, Source
from app.collector.store import StoreResult, store
from app.core.config import Settings

logger = logging.getLogger("zubi.collector")


@dataclass(frozen=True)
class SourceRun:
    source: str
    ok: bool
    result: StoreResult | None = None
    error: str | None = None
    seconds: float = 0.0


def build_sources(settings: Settings) -> list[Source]:
    sources: list[Source] = []
    if settings.seoul_api_key:
        sources.append(SeoulSource(settings.seoul_api_key))
    else:
        logger.warning("SEOUL_API_KEY 없음 — 서울 수집 건너뜀")
    if settings.gg_api_key:
        sources.append(GyeonggiSource(settings.gg_api_key))
    else:
        logger.warning("GG_API_KEY 없음 — 경기 수집 건너뜀")
    return sources


def build_http_client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        timeout=settings.collector_http_timeout_seconds,
        transport=httpx.HTTPTransport(retries=settings.collector_http_retries),
        headers={"User-Agent": "zubi-collector/0.1"},
    )


def collect_once(
    sources: Iterable[Source],
    client: httpx.Client,
    session_factory: Callable[[], Session],
) -> list[SourceRun]:
    runs: list[SourceRun] = []
    for source in sources:
        started = time.monotonic()
        try:
            records = source.fetch(client)
            observed_at = datetime.now(UTC)
            with session_factory() as session, session.begin():
                result = store(session, records, observed_at)
        except Exception as e:  # noqa: BLE001 — 출처 하나의 실패로 루프를 멈추지 않는다
            elapsed = time.monotonic() - started
            logger.exception("[%s] 수집 실패 (%.1fs)", source.name, elapsed)
            runs.append(SourceRun(source.name, ok=False, error=repr(e), seconds=elapsed))
            continue
        elapsed = time.monotonic() - started
        logger.info(
            "[%s] 주차장 %d · 관측 %d · 새 스냅샷 %d (%.1fs)",
            source.name,
            result.lots,
            result.observations,
            result.snapshots_inserted,
            elapsed,
        )
        runs.append(SourceRun(source.name, ok=True, result=result, seconds=elapsed))
    return runs


def run_forever(
    sources: list[Source],
    client: httpx.Client,
    session_factory: Callable[[], Session],
    interval_seconds: int,
    stop: threading.Event,
) -> None:
    """interval 간격의 고정 박자로 실행. 한 회차가 길어져도 다음 박자로 맞춘다."""
    logger.info("수집기 시작: 출처 %s, 주기 %ds", [s.name for s in sources], interval_seconds)
    next_tick = time.monotonic()
    while not stop.is_set():
        collect_once(sources, client, session_factory)
        next_tick += interval_seconds
        now = time.monotonic()
        if next_tick < now:
            skipped = int((now - next_tick) // interval_seconds) + 1
            logger.warning("수집이 주기보다 길어 %d회 건너뜀", skipped)
            next_tick += skipped * interval_seconds
        stop.wait(next_tick - now)
    logger.info("수집기 종료")
