"""QAH-06: `AdminRoutes.jsx`의 실제 라우트인데 `scripts/ui_qa/routes.py`에 등록이 안 된
화면은 한 번도 캡처·검사되지 않는다 — 조사 도구가 "다 봤다"고 말해도 실제로는 못 본
화면이 있다(같은 결함이 `routes.py`의 "2026-08-08 추가" 주석에 이미 한 번 기록돼 있다:
system_admin 전용 4화면이 등록 누락으로 한 번도 캡처된 적이 없었다 — 그리고 이번 QAH
배치에서 `admin_mail`이 같은 방식으로 또 빠져 있었다). 같은 함정이 세 번째로 반복되지
않게 전수로 대조한다.

`AdminRoutes.jsx`의 JSX를 실제로 파싱하지 않고(빌드 도구 없이는 무리다) `<Route path=`
리터럴을 정규식으로 읽는다 — `test_ui_qa_harness_honesty.py`와 같은 "소스 텍스트를
직접 읽는다" 기법.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.ui_qa.routes import ALL_ROUTES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADMIN_ROUTES_JSX = PROJECT_ROOT / "frontend" / "src" / "app" / "AdminRoutes.jsx"

# 하네스가 정말로 커버할 필요가 없는 것들.
#   "*"       — Navigate 폴백, 화면이 아니다.
_IGNORED_PATHS = {"*"}


def _admin_route_paths() -> set[str]:
    src = ADMIN_ROUTES_JSX.read_text(encoding="utf-8")
    paths = set(re.findall(r'<Route\s+path="([^"]+)"', src))
    assert paths, "AdminRoutes.jsx에서 <Route path=...>를 하나도 못 찾았다 — 정규식이 깨졌다"
    return paths - _IGNORED_PATHS


def test_every_admin_route_is_registered_in_the_qa_harness():
    """관리자 콘솔의 실제 라우트가 전부 하네스 어딘가(관리자 목록이든, 공유 화면이면
    사용자 목록이든)에 hash_path로 등록돼 있는지 — 등록 안 된 화면은 캡처·콘솔·대비·
    반응형 검사를 전부 건너뛴다."""
    harness_paths = {r.hash_path for r in ALL_ROUTES}
    missing = _admin_route_paths() - harness_paths
    assert not missing, (
        f"AdminRoutes.jsx에 있는데 QA 하네스(scripts/ui_qa/routes.py)엔 없는 라우트: "
        f"{sorted(missing)} — 이 화면들은 QA 하네스가 몇 번을 돌아도 한 번도 캡처되지 않는다"
    )
