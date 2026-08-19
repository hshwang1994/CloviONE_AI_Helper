"""QAH-06: 소스에 있는 라우트가 `scripts/ui_qa/routes.py` 에 없으면 그 화면은 한 번도
캡처·검사되지 않는다 — 조사 도구가 "다 봤다"고 말해도 실제로는 못 본 화면이 있다.

같은 함정이 저장소에서 **네 번** 반복됐다: system_admin 전용 4화면 · `admin_mail` ·
`/audit/:id` · 그리고 사용자 콘솔의 `/my-approvals`·`/my-display`. 앞의 셋은 관리자
단방향 검사가 뒤늦게 잡았고, 마지막 둘은 **사용자 콘솔에 검사 자체가 없어서** 계획
세션의 전수 감사 전까지 아무도 몰랐다.

그래서 이 검사는 이제 세 방향이다 (W0).

  ① 소스 → 하네스   `UserRoutes.jsx` + `AdminRoutes.jsx` 의 라우트가 전부 등록돼 있는가
  ② 하네스 → 소스   하네스에만 있는 유령 경로가 없는가 (화면이 사라졌는데 목록에 남은 것)
  ③ 리다이렉트 분류 소스가 `<Navigate>` 인 경로는 **화면이 아니라 별칭**으로 등록됐는가

③ 이 없으면 `/system`·`/notion-console`·`/llm-console`·`/maintenance` 처럼 리다이렉트인
경로가 화면으로 세어진다 — PNG 는 도착지 화면인데 21개 검사가 전부 거기서 통과하고,
커버리지는 한 화면을 둘로 센다. 통과하는 검사가 늘어나는 방향의 오류라 눈에 안 띈다.

JSX 를 실제로 파싱하지 않고(빌드 도구 없이는 무리다) `<Route path=` 리터럴을 정규식으로
읽는다 — `test_ui_qa_harness_honesty.py` 와 같은 "소스 텍스트를 직접 읽는다" 기법.
**계산된 경로**(`path={"/" + key}` 의 REGISTRY 28키, `TAB_GROUPS` 의 그릇·옛 주소)는
정규식이 볼 수 없다. 그쪽 대조는 JS 가 JS 로 증명한다 —
`frontend/src/screens/registry-surface-parity.test.js`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.ui_qa.routes import ALIAS_ROUTES, ALL_ROUTES

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP = PROJECT_ROOT / "frontend" / "src" / "app"
ADMIN_ROUTES_JSX = APP / "AdminRoutes.jsx"
USER_ROUTES_JSX = APP / "UserRoutes.jsx"

# 하네스가 정말로 커버할 필요가 없는 것.
#   "*"  — catch-all 폴백, 화면이 아니다.
_IGNORED_PATHS = {"*"}

_ROUTE_RE = re.compile(r'<Route\s+path="([^"]+)"')
# `<Route path="/system" element={<Navigate to="/settings?tab=os" replace />} />`
_NAVIGATE_RE = re.compile(
    r'<Route\s+path="([^"]+)"\s+element=\{\s*<Navigate\s+to="([^"]+)"'
)


def _literal_paths(jsx: Path) -> set[str]:
    src = jsx.read_text(encoding="utf-8")
    paths = set(_ROUTE_RE.findall(src))
    assert paths, f"{jsx.name} 에서 <Route path=...> 를 하나도 못 찾았다 — 정규식이 깨졌다"
    return paths - _IGNORED_PATHS


def _navigate_pairs() -> dict[str, str]:
    src = ADMIN_ROUTES_JSX.read_text(encoding="utf-8")
    return dict(_NAVIGATE_RE.findall(src))


def _base(path: str) -> str:
    """쿼리를 뗀 경로. 하네스는 탭·검색 상태를 `?tab=`·`?q=` 로 구분해 등록한다."""
    return path.split("?", 1)[0]


def _harness_paths(routes) -> set[str]:
    out: set[str] = set()
    for r in routes:
        out.add(_base(r.hash_path))
        if r.hash_template:
            # `/tickets/{id}` ↔ 소스의 `/tickets/:id`
            out.add(_base(re.sub(r"\{[^}]+\}", ":id", r.hash_template)))
    return out


def test_every_source_route_is_registered_in_the_qa_harness():
    """① 소스 → 하네스. 등록 안 된 화면은 캡처·콘솔·대비·반응형 검사를 전부 건너뛴다."""
    source = _literal_paths(ADMIN_ROUTES_JSX) | _literal_paths(USER_ROUTES_JSX)
    harness = _harness_paths(ALL_ROUTES) | _harness_paths(ALIAS_ROUTES)
    missing = {p for p in source if _base(p) not in harness}
    assert not missing, (
        "소스에 있는데 QA 하네스(scripts/ui_qa/routes.py)엔 없는 라우트: "
        f"{sorted(missing)} — 이 화면들은 하네스가 몇 번을 돌아도 한 번도 캡처되지 않는다"
    )


def test_the_harness_has_no_ghost_routes():
    """② 하네스 → 소스. 화면이 사라졌는데 목록에 남으면 리다이렉트나 404 를 찍는다.

    계산된 경로(REGISTRY 28키·TAB_GROUPS 그릇과 옛 주소)는 정규식이 못 보므로,
    소스 텍스트에 그 경로 문자열이 **어떤 형태로든** 나타나는지까지 본다
    (`registry/*.js` 의 `key: "audit"`, `TAB_GROUPS` 의 `path: "/backup"`).
    엄격도를 낮춘 대신 "완전히 사라진 경로"는 확실히 잡는다.
    """
    haystack = "\n".join(
        p.read_text(encoding="utf-8")
        for p in [ADMIN_ROUTES_JSX, USER_ROUTES_JSX]
        + sorted((PROJECT_ROOT / "frontend" / "src" / "screens" / "registry").glob("*.js"))
    )
    ghosts = []
    for r in ALL_ROUTES + ALIAS_ROUTES:
        if r.console == "public":
            continue  # 로그인은 서버가 그리는 Jinja 화면이라 라우터에 없다
        base = _base(r.hash_path).lstrip("/")
        if not base:
            continue
        key = base.split("/")[0]
        if key not in haystack:
            ghosts.append(r.id)
    assert not ghosts, (
        f"하네스에만 있고 소스 어디에도 없는 라우트: {sorted(ghosts)} — "
        "화면이 사라졌는데 목록이 남으면 리다이렉트나 404 를 찍고 검사는 거기서 통과한다"
    )


def test_redirect_only_paths_are_registered_as_aliases_not_screens():
    """③ 소스가 `<Navigate>` 인 경로는 별칭이어야 한다.

    이걸 화면으로 등록하면 도착지 화면의 PNG 가 한 장 더 생기고 그 위에서 모든 검사가
    통과한다 — 커버리지가 늘어나는 방향의 거짓이라 요약만 보면 오히려 좋아 보인다.
    """
    pairs = _navigate_pairs()
    assert pairs, "AdminRoutes.jsx 에서 <Navigate> 라우트를 하나도 못 찾았다 — 정규식이 깨졌다"

    screens = {_base(r.hash_path) for r in ALL_ROUTES}
    misfiled = sorted(p for p in pairs if _base(p) in screens)
    assert not misfiled, (
        f"소스는 리다이렉트인데 하네스가 화면으로 등록했다: {misfiled} — "
        "찍히는 것은 도착지 화면이고 검사는 전부 거기서 통과한다"
    )

    aliases = {_base(r.hash_path): r for r in ALIAS_ROUTES}
    unregistered = sorted(p for p in pairs if _base(p) not in aliases)
    assert not unregistered, (
        f"소스의 리다이렉트가 ALIAS_ROUTES 에 없다: {unregistered} — "
        "옛 주소가 조용히 죽어도 아무도 모른다"
    )

    for path, target in pairs.items():
        got = aliases[_base(path)].alias_of
        assert got == target, (
            f"{path} 의 도착지가 소스와 다르다: 하네스={got!r} 소스={target!r}"
        )


def test_aliases_are_not_counted_as_screens():
    """별칭이 `ALL_ROUTES` 에 섞이면 위 ③ 이 무의미해진다 — 경계 자체를 고정한다."""
    overlap = {r.id for r in ALIAS_ROUTES} & {r.id for r in ALL_ROUTES}
    assert not overlap, f"별칭이 화면 목록에도 있다: {sorted(overlap)}"
    assert all(not r.alias_of for r in ALL_ROUTES), (
        "ALL_ROUTES 에 alias_of 를 가진 항목이 있다 — 화면과 별칭이 섞였다"
    )
    assert all(r.alias_of for r in ALIAS_ROUTES), "ALIAS_ROUTES 에 도착지 없는 항목이 있다"
