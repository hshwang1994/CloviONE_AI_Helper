"""ChatGPT 연결 도우미는 다시 생기지 않는다 (D-540).

연결 도우미(PowerShell · Python)와 쿠키 없는 `/api/connect/*` 문은 붙여 넣기 로그인으로 바꾸며 걷었다. 도우미는 관리자 PC
에서 명령을 실행하게 하고, 세션 · CSRF 밖의 쓰기 문을 열어 두어야 했다. 같은 일을 붙여 넣기 하나가 설치 없이 한다.

못박는 성질:
1. 도우미 파일과 그 디렉터리가 저장소에 없다.
2. 앱에 `/api/connect` · `/connect/` 로 시작하는 경로가 없다.
3. 제품 코드가 도우미 모듈을 들여오지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

ROOT = Path(__file__).resolve().parents[2]


def test_the_helper_files_are_not_in_the_repository():
    assert not (ROOT / "tools" / "connect").exists()
    assert not (ROOT / "app" / "ai" / "connect_router.py").exists()


def test_the_app_has_no_helper_door(app):
    paths = [getattr(route, "path", "") for route in app.routes]
    assert not [p for p in paths if p.startswith("/api/connect") or p.startswith("/connect/")], paths


def test_product_code_does_not_import_the_helper():
    offenders = []
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "connect_router" in text or "clovirassist-connect" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders
