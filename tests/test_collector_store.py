"""DB 통합 테스트. TEST_DATABASE_URL(없으면 .env의 DATABASE_URL)의 PostGIS가 필요하다.

DB가 없으면 건너뛴다. 테스트는 트랜잭션 안에서 돌고 끝나면 롤백한다.
"""

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.collector.sources.base import KST, LotRecord, Observation
from app.collector.store import store
from app.core.config import get_settings
from app.db.models import LotSnapshot, ParkingLot

DB_URL = os.environ.get("TEST_DATABASE_URL") or get_settings().database_url


@pytest.fixture
def session():
    engine = create_engine(DB_URL)
    try:
        conn = engine.connect()
    except OperationalError:
        pytest.skip("PostGIS DB 없음 (docker compose up -d db 후 alembic upgrade head)")
    has_schema = conn.execute(text("select to_regclass('lot_snapshot')")).scalar()
    conn.rollback()
    if not has_schema:
        conn.close()
        pytest.skip("스키마 없음 (uv run alembic upgrade head)")
    trans = conn.begin()
    sess = Session(bind=conn, join_transaction_mode="create_savepoint")
    yield sess
    sess.close()
    trans.rollback()
    conn.close()


def make_record(available: int, provided_at: datetime, **kw) -> LotRecord:
    return LotRecord(
        source="test",
        source_id=kw.pop("source_id", "lot-1"),
        name=kw.pop("name", "테스트 주차장"),
        realtime=True,
        total_spaces=100,
        observation=Observation(provided_at, available, 100 - available, 100),
        **kw,
    )


def test_store_upserts_lot_and_dedupes_snapshots(session: Session) -> None:
    t0 = datetime(2026, 11, 20, 9, 0, tzinfo=KST)
    now = datetime.now(UTC)

    r1 = store(session, [make_record(40, t0)], now)
    assert (r1.lots, r1.observations, r1.snapshots_inserted) == (1, 1, 1)

    # 출처가 갱신하지 않음(같은 provided_at) → 새 스냅샷 없음, 이름은 갱신
    r2 = store(session, [make_record(40, t0, name="새 이름")], now + timedelta(minutes=5))
    assert r2.snapshots_inserted == 0

    lot = session.scalars(select(ParkingLot).where(ParkingLot.source == "test")).one()
    assert lot.name == "새 이름"

    r3 = store(
        session,
        [make_record(35, t0 + timedelta(minutes=5), name="새 이름")],
        now + timedelta(minutes=10),
    )
    assert r3.snapshots_inserted == 1
    assert r3.lots == 1
    snaps = session.scalars(
        select(LotSnapshot).where(LotSnapshot.lot_id == lot.id).order_by(LotSnapshot.provided_at)
    ).all()
    assert [s.available_spaces for s in snaps] == [40, 35]


def test_store_does_not_overwrite_geom(session: Session) -> None:
    t0 = datetime(2026, 11, 20, 9, 0, tzinfo=KST)
    store(session, [make_record(40, t0)], datetime.now(UTC))
    session.execute(
        text(
            "update parking_lot set geom = ST_SetSRID(ST_MakePoint(126.97, 37.57), 4326) "
            "where source = 'test'"
        )
    )
    store(session, [make_record(30, t0 + timedelta(minutes=5))], datetime.now(UTC))
    has_geom = session.execute(
        text("select geom is not null from parking_lot where source = 'test'")
    ).scalar()
    assert has_geom
