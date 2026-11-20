# Zubi-Server

Zubi 백엔드 API 서버 (FastAPI) + 공공 주차 실시간 데이터 수집기.

## 스택

- Python 3.13 (`uv`로 관리)
- FastAPI, pydantic-settings
- PostgreSQL + PostGIS, SQLAlchemy 2 (psycopg 3), GeoAlchemy2, Alembic
- httpx (공공 API 호출)
- pytest, ruff

## 구조

```
app/
├── main.py                # FastAPI 앱 생성, CORS, 라우터 등록
├── core/config.py         # 환경 변수 기반 설정 (.env)
├── api/v1/router.py       # v1 라우터 묶음
├── api/v1/endpoints/      # 엔드포인트 모듈
├── schemas/               # Pydantic 스키마
├── db/
│   ├── models.py          # parking_lot, lot_snapshot (API·수집기 공용)
│   └── session.py         # 엔진·세션
└── collector/             # 수집기 (API와 별도 프로세스)
    ├── __main__.py        # python -m app.collector [--once] [--interval N]
    ├── runner.py          # 주기 실행, 출처별 장애 격리
    ├── store.py           # 주차장 upsert + 스냅샷 insert
    ├── log.py             # 로그 설정 (API 키 가림)
    └── sources/           # seoul.py (시영 실시간), gg.py (경기 가용정보)
migrations/                # Alembic
deploy/                    # systemd 유닛 예시
tests/
```

## 시작하기

```bash
uv sync
```

```bash
cp .env.example .env
```

`.env`에 `SEOUL_API_KEY`, `GG_API_KEY`를 채운다 (Doc/11_API_키.md, 커밋 금지).

로컬 DB (Docker):

```bash
docker compose up -d db
```

```bash
uv run alembic upgrade head
```

API 서버:

```bash
uv run fastapi dev app/main.py
```

- API: http://localhost:8000/api/v1/health
- 문서: http://localhost:8000/docs

에뮬레이터·외부 기기에서 접근하려면 `--host 0.0.0.0`을 붙여 실행하세요.

## 수집기

서울 시영주차장 실시간(`GetParkingInfo`)과 경기 교통정보센터 가용정보를
`COLLECTOR_INTERVAL_SECONDS`(기본 300초)마다 호출해 DB에 쌓는다.

```bash
uv run python -m app.collector --once
```

```bash
uv run python -m app.collector
```

- 출처 한 줄 → `parking_lot` 한 행 (`source`, `source_id`로 upsert). 출처가 주는 필드만 갱신하고
  `geom` 등 다른 단계가 채우는 값은 덮어쓰지 않는다.
- 실시간 값 → `lot_snapshot` 한 행. 같은 주차장·같은 `provided_at`(출처 갱신 시각)은 한 번만 저장.
- 서울은 `PRK_STTS_YN = 1`(실시간 연계)인 곳만 스냅샷을 만든다. 서울 응답에는 좌표가 없어 `geom`은 비어 있다.
- 경기 `source_id`는 `{laeId}-{pkplcId}` (`pkplcId`가 시·군 안에서만 고유).
- 한 출처가 실패해도 다른 출처는 계속 수집한다. `--once`는 실패 출처가 있으면 종료 코드 1.
- 서버에서는 API와 별도 서비스로 등록한다: `deploy/zubi-collector.service`.

## 테스트 / 린트

```bash
uv run pytest
```

DB 테스트(`tests/test_collector_store.py`)는 PostGIS가 떠 있고 마이그레이션이 적용돼 있을 때만 돈다.
다른 DB를 쓰려면 `TEST_DATABASE_URL`을 지정한다.

```bash
uv run ruff check . && uv run ruff format .
```
