"""smoke 마커 전용 fixture — **살아 있는 서버**가 있어야 도는 진짜 브라우저 테스트다 (`QA-02`).

`pytest.ini`가 이미 `-m "not smoke"`로 기본 제외한다(`smoke: ... deselected by default`).
서버가 없으면(로컬 dev 미기동, CI 등) 실패가 아니라 **skip**으로 정직하게 빠진다 — 이 파일이
비어 있던 것 자체가 `QA-02`였다("실브라우저 E2E가 수행된 적 없다").

대상: `SMOKE_BASE_URL` 환경변수(기본 로컬 dev `.env`와 같은 `http://127.0.0.1:8099`). 승인된
TEST SERVER를 겨눌 때는 `SMOKE_BASE_URL=https://<host>` + `UI_QA_EMAIL`/`UI_QA_PASSWORD`를
넘긴다(`scripts/ui_qa/auth.py`와 동일한 계약 — 원격 대상에는 계정을 새로 만들지 않는다).
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SMOKE_BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8099")


def _server_reachable(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/readyz", timeout=3) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001 — 도달 불가의 모든 사유는 같은 결론(skip)으로 수렴한다
        return False


@pytest.fixture(scope="session")
def smoke_base_url() -> str:
    if not _server_reachable(SMOKE_BASE_URL):
        pytest.skip(
            f"살아 있는 서버가 없어 smoke를 건너뜀: {SMOKE_BASE_URL} (/readyz 응답 없음). "
            "로컬 dev를 띄우거나 SMOKE_BASE_URL로 대상을 지정하세요."
        )
    return SMOKE_BASE_URL


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(scope="session")
def qa_session(browser, smoke_base_url):
    from scripts.ui_qa.auth import ensure_session

    return ensure_session(browser, smoke_base_url, REPO_ROOT / "dist" / "smoke-session", log=print)
