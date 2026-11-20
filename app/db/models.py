"""DB 모델 — API와 수집기가 함께 쓴다 (Doc 08번 §6 DB 초안 기준)."""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ParkingLot(Base):
    """주차장 마스터. 출처(source)별 원본 ID(source_id)로 한 행.

    수집기는 출처가 주는 필드만 갱신한다. `geom`처럼 다른 단계(지오코딩·마스터 통합)가
    채우는 값은 수집기가 덮어쓰지 않는다.
    """

    __tablename__ = "parking_lot"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_parking_lot_source"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(16))  # seoul | gg | kotsa | kakao
    source_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(50))  # 경기: 시·군명
    address: Mapped[str | None] = mapped_column(String(300))
    # 인덱스는 아래 ix_parking_lot_geom으로 직접 만든다 (GeoAlchemy 자동 인덱스와 중복 방지)
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=True)
    total_spaces: Mapped[int | None] = mapped_column(Integer)
    # 요금: 원 / 분 단위 (출처 원값 그대로)
    fee_basic: Mapped[int | None] = mapped_column(Integer)
    fee_basic_min: Mapped[int | None] = mapped_column(Integer)
    fee_add: Mapped[int | None] = mapped_column(Integer)
    fee_add_min: Mapped[int | None] = mapped_column(Integer)
    fee_day_max: Mapped[int | None] = mapped_column(Integer)
    hours: Mapped[dict | None] = mapped_column(JSONB)
    type: Mapped[str | None] = mapped_column(String(10))  # 노상 | 노외 | 부설
    has_ev: Mapped[bool | None] = mapped_column(Boolean)
    realtime: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


Index("ix_parking_lot_geom", ParkingLot.geom, postgresql_using="gist")


class LotSnapshot(Base):
    """수집기가 주기마다 쌓는 실시간 관측값.

    - observed_at: 수집기가 API를 호출한 시각
    - provided_at: 출처가 알려 준 데이터 갱신 시각 (observed_at − provided_at = 지연 Δ_lag)
    같은 주차장의 같은 provided_at은 한 번만 저장한다 (출처가 갱신하지 않았는데
    다시 저장하면 추세 r̂ 계산 때 "변화 없음" 표본이 중복된다).
    """

    __tablename__ = "lot_snapshot"
    __table_args__ = (
        UniqueConstraint("lot_id", "provided_at", name="uq_lot_snapshot_lot_provided"),
        Index("ix_lot_snapshot_lot_observed", "lot_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("parking_lot.id", ondelete="CASCADE")
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_spaces: Mapped[int] = mapped_column(Integer)
    occupied: Mapped[int | None] = mapped_column(Integer)
    total_spaces: Mapped[int | None] = mapped_column(Integer)
