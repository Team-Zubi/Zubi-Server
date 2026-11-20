"""수집기 실행: API와 별도 프로세스.

uv run python -m app.collector          # 주기 실행 (COLLECTOR_INTERVAL_SECONDS)
uv run python -m app.collector --once   # 한 번만 실행하고 종료 (실패 출처가 있으면 종료 코드 1)
"""

import argparse
import signal
import sys
import threading

from app.collector.log import setup_logging
from app.collector.runner import build_http_client, build_sources, collect_once, run_forever
from app.core.config import get_settings
from app.db.session import get_sessionmaker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.collector")
    parser.add_argument("--once", action="store_true", help="한 번만 수집하고 종료")
    parser.add_argument("--interval", type=int, help="주기(초). 기본은 설정값")
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging([settings.seoul_api_key, settings.gg_api_key])

    sources = build_sources(settings)
    if not sources:
        print("수집할 출처가 없습니다. .env에 SEOUL_API_KEY / GG_API_KEY를 넣으세요.")
        return 2

    session_factory = get_sessionmaker()
    with build_http_client(settings) as client:
        if args.once:
            runs = collect_once(sources, client, session_factory)
            return 0 if all(r.ok for r in runs) else 1

        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        run_forever(
            sources,
            client,
            session_factory,
            args.interval or settings.collector_interval_seconds,
            stop,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
