# Zubi-Server

Zubi 백엔드 API 서버 (FastAPI).

## 스택

- Python 3.13 (`uv`로 관리)
- FastAPI, pydantic-settings
- pytest, ruff

## 구조

```
app/
├── main.py                # FastAPI 앱 생성, CORS, 라우터 등록
├── core/config.py         # 환경 변수 기반 설정 (.env)
├── api/v1/router.py       # v1 라우터 묶음
├── api/v1/endpoints/      # 엔드포인트 모듈
└── schemas/               # Pydantic 스키마
tests/
```

## 시작하기

```bash
uv sync
```

```bash
cp .env.example .env
```

```bash
uv run fastapi dev app/main.py
```

- API: http://localhost:8000/api/v1/health
- 문서: http://localhost:8000/docs

에뮬레이터·외부 기기에서 접근하려면 `--host 0.0.0.0`을 붙여 실행하세요.

## 테스트 / 린트

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format .
```
