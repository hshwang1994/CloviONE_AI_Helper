"""문서 깃발(`team_docs_enabled`)은 문서 API **전부**를 막아야 한다 (P-84).

`tests/security/test_maintenance_coverage.py` 와 같은 방식이다 — grep 이 아니라 **FastAPI 가
실제로 만든 의존성 그래프**를 걸어서 확인한다. 라우터 단위로 걸었든 라우트 단위로 걸었든
무관하고, 새 라우트를 추가하면서 빠뜨리면 여기서 잡힌다.

**왜 필요했나.** `require_team_docs_enabled` 는 옛 미러 라우터(`/api/team-docs`)에만 걸려
있었다. 정본 문서 API 는 `/api/knowledge/*` 인데 그쪽은 열려 있었다 — 깃발을 끈 테넌트에서
사이드바 메뉴는 사라지고 `/api/me` 는 `team_docs_enabled: false` 라고 답하는데, 공유받은
`#/knowledge/<id>` 는 정상적으로 열렸다. 운영자는 「문서를 껐다」고 믿고 서버는 문서를 전부
내줬다. 개별 엔드포인트 시험(`test_feature_flag_off_hides_team_docs`)은 옛 라우터 하나만
쳤기 때문에 이 구멍을 구조적으로 볼 수 없었다.

**반례가 있다.** 게이트가 없어야 하는 곳(`/api/tickets`·`/api/trash`)에 게이트가 **없다**는
것도 같은 걸음으로 확인한다 — 그래야 이 검사가 「있음」과 「없음」을 실제로 구별한다는
사실이 증명된다. 이름만 보고 언제나 초록을 내는 검사는 아무것도 지키지 않는다.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

GATE = "require_team_docs_enabled"

# 문서 깃발이 막아야 하는 것: 정본 문서 API 와 옛 미러 API, 둘 다.
GATED_PREFIXES = ("/api/knowledge", "/api/team-docs")

# 막으면 안 되는 것 — 이유를 함께 적는다.
UNGATED_PREFIXES: dict[str, str] = {
    "/api/tickets": "티켓은 문서 깃발과 무관한 다른 기능이다",
    # 결정은 `app/core/feature_gate.py` 머리말에 있다. 휴지통은 티켓과 문서를 한 목록에
    # 담으므로 문서 깃발로 막으면 문서를 끈 테넌트가 티켓 휴지통까지 잃는다.
    "/api/trash": "휴지통은 티켓도 담는다 — 문서 깃발로 막으면 티켓 휴지통까지 닫힌다",
}


def _dependency_names(route: APIRoute) -> set[str]:
    names: set[str] = set()

    def walk(dep) -> None:
        for sub in dep.dependencies:
            names.add(getattr(sub.call, "__name__", ""))
            walk(sub)

    walk(route.dependant)
    return names


def _api_routes(app):
    for route in app.routes:
        if isinstance(route, APIRoute):
            yield route


def _label(route: APIRoute) -> str:
    return f"{sorted(route.methods)} {route.path}"


def test_every_document_route_passes_the_feature_flag_gate(app):
    routes = [r for r in _api_routes(app) if r.path.startswith(GATED_PREFIXES)]
    # 표본 수를 못박는다 — 라우터가 안 떠서 0건이면 「빠진 것이 없다」로 초록이 난다.
    knowledge = [r for r in routes if r.path.startswith("/api/knowledge")]
    legacy = [r for r in routes if r.path.startswith("/api/team-docs")]
    assert len(knowledge) >= 40, f"정본 문서 라우트가 {len(knowledge)}개뿐이다 — 라우터가 안 떴다"
    assert len(legacy) >= 8, f"옛 문서 라우트가 {len(legacy)}개뿐이다 — 라우터가 안 떴다"

    missing = [_label(r) for r in routes if GATE not in _dependency_names(r)]
    assert missing == [], (
        "문서 깃발을 꺼도 열려 있는 문서 라우트가 있다.\n"
        "APIRouter(dependencies=[Depends(require_team_docs_enabled), ...]) 를 빠뜨렸을 가능성이 크다:\n  "
        + "\n  ".join(sorted(missing))
    )


def test_every_resource_family_under_knowledge_is_gated(app):
    """자원 가족별로 **최소 한 라우트씩** 실제로 있는지 본다.

    위 시험은 「있는 라우트는 전부 지난다」를 재고, 이 시험은 「그 라우트들이 실제로
    있다」를 잰다 — 라우터에서 자원 하나가 통째로 빠져도 위 시험은 초록이다.
    """
    families = (
        "spaces", "folders", "documents", "templates", "tags", "categories",
        "attachments", "comments", "favorite", "versions", "relations",
    )
    paths = [r.path for r in _api_routes(app) if r.path.startswith("/api/knowledge")]
    for family in families:
        assert any(f"/{family}" in p for p in paths), (
            f"/api/knowledge 아래 '{family}' 라우트가 하나도 없다 — 가족 목록이나 라우터를 확인하라"
        )


def test_unrelated_routes_do_not_carry_the_document_gate(app):
    """반례. 이 게이트는 문서 API 에만 걸려야 한다.

    `/api/tickets` 는 표본으로, 그리고 `/api/trash` 는 **결정**으로 — 휴지통이 문서 깃발에
    걸리면 그 순간 이 시험이 빨개지고, 그것을 풀려면 `app/core/feature_gate.py` 의 결정을
    먼저 뒤집어야 한다.
    """
    for prefix, reason in UNGATED_PREFIXES.items():
        routes = [r for r in _api_routes(app) if r.path.startswith(prefix)]
        assert len(routes) >= 3, f"{prefix} 라우트가 {len(routes)}개뿐이다 — 반례가 될 수 없다"
        gated = [_label(r) for r in routes if GATE in _dependency_names(r)]
        assert gated == [], (
            f"{prefix} 가 문서 깃발에 걸려 있다({reason}):\n  " + "\n  ".join(sorted(gated))
        )


def test_the_gate_is_one_function_shared_by_both_routers():
    """두 라우터가 **같은 객체**를 건다. 베낀 사본이면 문구·기본값이 갈라지고 한쪽만 고치는
    날이 온다 — 옛 import 경로(`app.team_docs.router`)도 그 하나를 가리켜야 한다."""
    from app.core import feature_gate
    from app.team_docs import router as legacy_router

    assert legacy_router.require_team_docs_enabled is feature_gate.require_team_docs_enabled
    assert feature_gate.require_team_docs_enabled.__name__ == GATE
