"""상태를 바꾸는 라우트는 하나도 빠짐없이 CSRF 검사를 지나야 한다.

왜 테스트로 고정하는가: 지금은 라우터마다 `APIRouter(dependencies=[..., Depends(require_csrf)])`
로 걸려 있다. 라우터 단위라 새 라우트를 그 안에 추가하면 자동으로 보호되지만, **새 라우터를
만들면서 그 한 줄을 빠뜨리면 아무도 모른다.** 143개 중 하나만 빠져도 알아채기 어렵고,
빠진 채로 운영에 나가면 그 경로만 조용히 뚫린다.

grep 으로는 확인할 수 없다는 것도 실제로 확인했다 — `APIRouter(` 뒤 여러 줄에 걸쳐
의존성이 나열되면 정규식이 놓친다. 그래서 **FastAPI 가 실제로 만든 의존성 그래프**를 본다.
같은 이유로, 이 테스트는 "어떻게 걸었는지"에 무관하다: 라우터 단위든 라우트 단위든
전역이든, 실행 시점에 require_csrf 를 지나기만 하면 통과다.

지금 SameSite=strict 라 크로스사이트 요청에는 세션 쿠키가 아예 실리지 않는다. 그래서
이건 오늘의 구멍이 아니라 **두 번째 방어선**이다. 누군가 임베드나 외부 연동 때문에
SameSite 를 완화하는 날, 이 테스트가 없으면 그 순간 빠진 라우트가 전부 열린다.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

# 세션이 없는 상태에서 부르는 경로. require_csrf 는 세션의 csrf_token 과 비교하므로
# 여기에는 걸 수 없다. 대신 각자 다른 방어가 있어야 하고, 그것도 아래에서 확인한다.
EXEMPT: dict[str, str] = {
    "/login": "세션이 생기기 전이라 CSRF 토큰이 없다 — Origin 검사로 막는다",
}


def _dependency_names(route: APIRoute) -> set[str]:
    """이 라우트를 처리할 때 실제로 실행되는 의존성 이름 전부(하위까지)."""
    names: set[str] = set()

    def walk(dep) -> None:
        for sub in dep.dependencies:
            names.add(getattr(sub.call, "__name__", ""))
            walk(sub)

    walk(route.dependant)
    return names


def _write_routes(app) -> list[tuple[APIRoute, set[str]]]:
    out = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not (route.methods - SAFE_METHODS):
            continue
        out.append((route, _dependency_names(route)))
    return out


def test_every_write_route_checks_csrf(app):
    routes = _write_routes(app)
    assert len(routes) > 100, f"쓰기 라우트가 {len(routes)}개뿐이다 — 앱이 제대로 안 떴다"

    missing = [
        f"{sorted(r.methods - SAFE_METHODS)} {r.path}"
        for r, names in routes
        if "require_csrf" not in names and r.path not in EXEMPT
    ]
    assert not missing, (
        "CSRF 검사를 지나지 않는 쓰기 라우트가 있다. 새 라우터를 만들면서\n"
        "APIRouter(dependencies=[..., Depends(require_csrf)]) 를 빠뜨렸을 가능성이 크다:\n  "
        + "\n  ".join(missing)
    )


def test_exempt_routes_have_another_defence(app):
    """예외로 둔 경로는 '아무 방어가 없어도 된다'는 뜻이 아니다."""
    by_path = {r.path: names for r, names in _write_routes(app)}
    for path, reason in EXEMPT.items():
        assert path in by_path, f"예외 목록에 있는 {path} 가 사라졌다 — 목록을 정리하라"
        names = by_path[path]
        assert any("origin" in n.lower() for n in names), (
            f"{path} 는 CSRF 예외인데({reason}) Origin 검사도 없다"
        )


def test_login_is_the_only_unauthenticated_write_route(app):
    """인증 없이 상태를 바꿀 수 있는 경로가 늘어나면 즉시 알아야 한다."""
    open_routes = []
    for route, names in _write_routes(app):
        authed = any(
            key in n
            for n in names
            for key in ("current_user", "current_auth", "require_role")
        )
        if not authed:
            open_routes.append(f"{sorted(route.methods - SAFE_METHODS)} {route.path}")
    assert open_routes == ["['POST'] /login"], (
        "인증 없이 부를 수 있는 쓰기 라우트 목록이 달라졌다:\n  " + "\n  ".join(open_routes)
    )
