"""수집 결과를 DB에 쓴다: 주차장 마스터 upsert → 스냅샷 insert (중복 provided_at은 건너뜀)."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.collector.sources.base import LotRecord
from app.db.models import LotSnapshot, ParkingLot


@dataclass(frozen=True)
class StoreResult:
    lots: int
    observations: int
    snapshots_inserted: int


def upsert_lots(session: Session, records: list[LotRecord]) -> dict[tuple[str, str], int]:
    """(source, source_id) → parking_lot.id. 출처가 주는 필드만 갱신한다."""
    ids: dict[tuple[str, str], int] = {}
    by_fields: dict[tuple[str, ...], list[LotRecord]] = defaultdict(list)
    for r in records:
        by_fields[r.master_fields].append(r)

    for fields, group in by_fields.items():
        # 같은 배치 안에 같은 키가 두 번 오면 ON CONFLICT가 실패하므로 마지막 값만 남긴다
        unique = {(r.source, r.source_id): r for r in group}
        rows = [
            {"source": r.source, "source_id": r.source_id, **{f: getattr(r, f) for f in fields}}
            for r in unique.values()
        ]
        stmt = insert(ParkingLot).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_parking_lot_source",
            set_={**{f: stmt.excluded[f] for f in fields}, "updated_at": func.now()},
        ).returning(ParkingLot.id, ParkingLot.source, ParkingLot.source_id)
        for lot_id, source, source_id in session.execute(stmt):
            ids[(source, source_id)] = lot_id
    return ids


def insert_snapshots(
    session: Session,
    records: list[LotRecord],
    lot_ids: dict[tuple[str, str], int],
    observed_at: datetime,
) -> int:
    rows = {}
    for r in records:
        if r.observation is None:
            continue
        lot_id = lot_ids[(r.source, r.source_id)]
        o = r.observation
        rows[(lot_id, o.provided_at)] = {
            "lot_id": lot_id,
            "observed_at": observed_at,
            "provided_at": o.provided_at,
            "available_spaces": o.available_spaces,
            "occupied": o.occupied,
            "total_spaces": o.total_spaces,
        }
    if not rows:
        return 0
    stmt = (
        insert(LotSnapshot)
        .values(list(rows.values()))
        .on_conflict_do_nothing(constraint="uq_lot_snapshot_lot_provided")
        .returning(LotSnapshot.id)
    )
    return len(session.execute(stmt).all())


def store(session: Session, records: list[LotRecord], observed_at: datetime) -> StoreResult:
    if not records:
        return StoreResult(0, 0, 0)
    lot_ids = upsert_lots(session, records)
    inserted = insert_snapshots(session, records, lot_ids, observed_at)
    return StoreResult(
        lots=len(lot_ids),
        observations=sum(1 for r in records if r.observation is not None),
        snapshots_inserted=inserted,
    )
