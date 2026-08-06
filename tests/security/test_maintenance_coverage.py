"""점검 모드는 **사용자 내용 쓰기 전부**를 막아야 한다 (N1/X6).

`tests/security/test_csrf_coverage.py` 와 같은 방식이다 — grep 이 아니라 **FastAPI 가 실제로
만든 의존성 그래프**를 걸어서 확인한다. 어떻게 걸었는지(라우터 단위/라우트 단위)에 무관하고,
새 라우트를 추가하면서 빠뜨리면 여기서 잡힌다.

**왜 필요했나.** `block_if_maintenance` 가 걸린 곳이 **정확히 2개**였다 —
`POST /api/conversations/{id}/messages` 와 `POST /api/messages/{id}/retry`, 둘 다 AI 채팅이다.
티켓·게시판·문서·팀채팅·놀이 쓰기는 **하나도 막히지 않았다.** 그런데 화면은 이렇게 말했다:

  * `Ops.jsx` "유지보수 모드가 켜져 있습니다, 사용자 쓰기(**티켓 생성, 변경 등**)가 차단되고 있습니다"
  * 확인 대화상자 "유지보수 모드를 켤까요? 사용자 쓰기가 차단됩니다."

**하필 유일하게 안 막히던 것을 예시로 들고 있었다.** 운영자가 점검 중이라 믿고 DB 를 만지는
동안 사용자 쓰기가 계속 들어온다 — 데이터 손상 경로다.

기존 테스트(`test_maintenance_mode.py`)는 AI 채팅 엔드포인트만 쳤기 때문에 이 구멍을 구조적으로
볼 수 없었다. 커버리지는 개별 엔드포인트 테스트가 아니라 이렇게 전수로 봐야 한다.

**주의:** `block_if_maintenance` 는 `user.role != ROLE_USER` 면 통과시킨다(operator+ 우회).
운영 실측(2026-08-05) 기준 사용자 15명 중 **admin 이 12명, user 는 2명**이다 — 즉 지금
점검 모드를 켜도 실제로 막히는 사람은 2명뿐이다. 게이트를 다 걸어도 그 사실은 변하지 않으니,
운영 안내 문구는 "일반 사용자 쓰기"라고 정확히 적어야 한다.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

# 점검 모드가 막아야 하는 것: **사용자가 내용을 만들거나 바꾸는 쓰기.**
GATED_PREFIXES = (
    "/api/tickets",
    # 프로젝트(0044). 티켓과 같은 이유로 막는다: 목표·일정·부서를 바꾸는 사용자 쓰기다.
    # 진행률 재계산은 특히 그렇다 — 점검 중이라 티켓 미러가 흔들리는 동안 계산한 값을
    # 저장해 버리면, 점검이 끝난 뒤 화면이 그 틀린 숫자를 정본이라고 말한다.
    "/api/projects",
    "/api/board",
    "/api/team-docs",
    "/api/team-chat",
    "/api/games",
    "/api/conversations",
    "/api/messages",
    "/api/trash",
)

# 막으면 안 되는 것 — 이유를 함께 적는다. 이유를 못 쓰면 예외로 두면 안 된다는 뜻이다.
EXEMPT_PREFIXES: dict[str, str] = {
    "/login": "로그인을 막으면 점검을 끝낼 관리자도 못 들어온다",
    "/logout": "나가는 것까지 막을 이유가 없다",
    # 세션이 없는 경로라 block_if_maintenance(get_current_user 의존) 를 걸 수 없고,
    # 걸 이유도 없다: 사용자 내용을 만들지 않고 미러도 건드리지 않는다. 반대로 막으면
    # 점검 중에 비밀번호를 잃은 사람이 점검이 끝날 때까지 갇힌다.
    "/forgot-password": "세션 없는 계정 복구 경로다. 내용 생성이 아니고 미러도 안 건드린다",
    "/reset-password": "세션 없는 계정 복구 경로다. 내용 생성이 아니고 미러도 안 건드린다",
    "/change-password": "만료된 비밀번호 때문에 로그인 직후 강제되는 경로다",
    "/api/admin": "점검 중에 써야 하는 관리 도구다(점검 모드를 끄는 것도 여기다)",
    "/api/me": "자기 계정·세션·환경설정. 내용 생성이 아니고 미러를 건드리지 않는다",
    "/api/notifications": "읽음 표시일 뿐 내용 생성이 아니다",
    "/api/announcements": "점검 공지 배너를 닫지도 못하게 되면 곤란하다",
}


def _dependency_names(route: APIRoute) -> set[str]:
    names: set[str] = set()

    def walk(dep) -> None:
        for sub in dep.dependencies:
            names.add(getattr(sub.call, "__name__", ""))
            walk(sub)

    walk(route.dependant)
    return names


def _write_routes(app):
    for route in app.routes:
        if isinstance(route, APIRoute) and (route.methods - SAFE_METHODS):
            yield route


def test_every_user_content_write_passes_the_maintenance_gate(app):
    routes = list(_write_routes(app))
    assert len(routes) > 100, f"쓰기 라우트가 {len(routes)}개뿐이다 — 앱이 제대로 안 떴다"

    missing = [
        f"{sorted(r.methods - SAFE_METHODS)} {r.path}"
        for r in routes
        if r.path.startswith(GATED_PREFIXES)
        and "block_if_maintenance" not in _dependency_names(r)
    ]
    assert not missing, (
        "점검 모드를 켜도 막히지 않는 사용자 쓰기 라우트가 있다.\n"
        "APIRouter(dependencies=[..., Depends(block_if_maintenance)]) 를 빠뜨렸을 가능성이 크다:\n  "
        + "\n  ".join(sorted(missing))
    )


def test_exempt_routes_are_deliberate(app):
    """예외 목록에 없는데 게이트도 없는 쓰기 라우트가 새로 생기면 알려 준다.

    새 기능을 만들면서 '이건 점검 중에 막아야 하나?'를 **한 번은 생각하게** 만드는 장치다.
    """
    unclassified = [
        f"{sorted(r.methods - SAFE_METHODS)} {r.path}"
        for r in _write_routes(app)
        if not r.path.startswith(GATED_PREFIXES)
        and not r.path.startswith(tuple(EXEMPT_PREFIXES))
    ]
    assert not unclassified, (
        "점검 모드 정책이 정해지지 않은 쓰기 라우트다. GATED_PREFIXES 에 넣든\n"
        "EXEMPT_PREFIXES 에 이유와 함께 넣든, 둘 중 하나를 골라야 한다:\n  "
        + "\n  ".join(sorted(unclassified))
    )
