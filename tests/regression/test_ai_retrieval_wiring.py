"""S10 이 만든 것이 **실제 실행 경로에 붙어 있는가** (회귀).

새 모듈을 만드는 것과 그것이 실제로 불리는 것은 다르다(CLAUDE.md §5). 여기서 지키는
배선 넷:

  * 🔴 **`/api/ai` 의 모든 경로에 권한 게이트가 있다.** 하나라도 빠지면 그 경로는
    로그인만으로 사내 문서를 뒤진다.
  * 🔴 **Gateway 가 프로세스에 하나다.** 요청마다 만들면 임베딩 Adapter 가 매번 새로
    생기고, 첫 호출에 ONNX 세션(S1 실측 2.3초)을 다시 만든다.
  * **마이그레이션 사슬이 이어져 있다** — `0008` 이 head 이고 `0007` 을 잇는다.
  * **화면이 라우트로 이어져 있다** — 파일만 만들고 라우트를 안 걸면 아무도 못 연다.
"""

from __future__ import annotations

import pathlib

import pytest

from app.ai.gateway import contract
from app.authz import permissions as perms

pytestmark = pytest.mark.regression

ROOT = pathlib.Path(__file__).resolve().parents[2]


# ── 권한 게이트 ──────────────────────────────────────────────────────────────


def _ai_routes(app):
    return [r for r in app.routes if getattr(r, "path", "").startswith("/api/ai/")]


def test_every_ai_route_is_gated(app):
    """게이트 없는 경로가 하나라도 있으면 그 경로는 로그인만으로 문서를 뒤진다."""
    routes = _ai_routes(app)
    assert routes, "AI 라우터가 안 붙어 있다"
    for route in routes:
        assert perms.AI_USE in _closure_names(route), f"{route.path} 에 AI_USE 게이트가 없다"

    # 🔴 **리더가 실제로 무언가를 읽었는지 먼저 본다** (D-213 1번). 위 반복문은 클로저를
    # 못 읽어도 조용히 통과할 수 있고, 그러면 「검사가 위반을 못 찾았다」와 「검사가
    # 아무것도 안 봤다」가 구별되지 않는다.
    other = next(r for r in app.routes if getattr(r, "path", "") == "/api/knowledge/spaces")
    assert perms.SPACE_READ in _closure_names(other)
    assert perms.AI_USE not in _closure_names(other)


def _closure_names(route) -> str:
    """이 경로가 실제로 요구하는 권한 이름들.

    `require_permission(...)` 는 클로저를 돌려주므로 이름이 아니라 **닫힌 변수**를 본다.
    문자열로 소스를 훑으면 주석에 적힌 이름까지 세어 「걸려 있다」고 잘못 말한다.
    """
    found: list[str] = []
    for dependency in _all_dependencies(route.dependant):
        call = dependency.call
        closure = getattr(call, "__closure__", None) or ()
        for cell in closure:
            value = cell.cell_contents
            if isinstance(value, frozenset):
                found.extend(str(v) for v in value)
    return "\n".join(found)


def _all_dependencies(dependant):
    yield dependant
    for child in dependant.dependencies:
        yield from _all_dependencies(child)


def test_writing_routes_require_csrf(app):
    """POST 는 세션 쿠키만으로 부를 수 있으면 안 된다."""
    for route in _ai_routes(app):
        if "POST" not in (route.methods or set()):
            continue
        names = {d.call.__name__ for d in _all_dependencies(route.dependant) if d.call}
        assert "require_csrf" in names, f"{route.path} 에 CSRF 게이트가 없다"


def test_the_search_route_never_calls_the_model(app):
    """생성이 막혀 있어도 검색이 도는 성질은 **라우터 모양**이 지킨다 (S10 Exit).

    검색 경로가 쿼터를 잡으면 그것은 모델을 부른다는 뜻이다 — 그 순간 「생성 없이도
    검색은 된다」가 성립하지 않는다.
    """
    source = (ROOT / "app" / "ai" / "router.py").read_text(encoding="utf-8")
    search_block = source.split("def ai_search(", 1)[1].split("\n@router", 1)[0]
    assert "consume(" not in search_block
    assert "answer_mod" not in search_block


# ── Gateway 단일 인스턴스 ────────────────────────────────────────────────────


def test_the_gateway_is_built_once_per_process(app):
    """요청마다 만들면 질의마다 ONNX 세션 로드(2.3초)를 다시 낸다."""
    assert isinstance(app.state.ai_gateway, contract.Gateway)


def test_the_router_reuses_the_process_gateway(client, app, login_as):
    login_as("user")
    marker = contract.Gateway(enabled=False)
    app.state.ai_gateway = marker
    assert client.get("/api/ai/status").status_code == 200
    # 라우터가 자기 것을 새로 만들었으면 이 단언이 깨진다.
    assert app.state.ai_gateway is marker


def test_building_the_gateway_never_raises(settings):
    """모델을 안 넣은 설치에서 앱이 아예 안 뜨는 것을 이 계약이 막는다."""
    from app.ai.gateway import registry

    assert isinstance(registry.build_gateway(settings), contract.Gateway)


# ── 마이그레이션 사슬 ────────────────────────────────────────────────────────


def test_the_retrieval_migration_follows_the_index_one():
    source = (
        ROOT / "alembic" / "versions" / "0008_ai_retrieval_indexes.py"
    ).read_text(encoding="utf-8")
    assert "revision = '0008_ai_retrieval'" in source
    assert "down_revision = '0007_ai_index'" in source


def test_no_revision_follows_the_retrieval_one():
    """`0008` 이 head 다. 두 갈래가 되면 `upgrade head` 가 어느 쪽인지 못 고른다."""
    versions = ROOT / "alembic" / "versions"
    followers = [
        path.name for path in versions.glob("*.py")
        if "down_revision = '0008_ai_retrieval'" in path.read_text(encoding="utf-8")
    ]
    assert followers == []


def test_no_vector_index_is_created_yet():
    """D-210: 임계(약 1.2만 벡터)를 넘기 전에는 만들지 않는다."""
    for path in (ROOT / "alembic" / "versions").glob("*.py"):
        body = path.read_text(encoding="utf-8").lower()
        assert "using hnsw" not in body
        assert "using ivfflat" not in body


# ── 화면 배선 ────────────────────────────────────────────────────────────────


def test_the_workspace_screen_is_reachable():
    """파일만 만들고 라우트를 안 걸면 아무도 못 연다."""
    routes = (ROOT / "frontend" / "src" / "app" / "UserRoutes.jsx").read_text(encoding="utf-8")
    assert 'path="/ai"' in routes
    assert "AiWorkspace" in routes


def test_the_workspace_belongs_to_the_user_console():
    """빠뜨리면 관리자군이 이 화면을 열 때 사이드바가 통째로 관리자 메뉴로 바뀐다."""
    nav = (ROOT / "frontend" / "src" / "app" / "navConfig.js").read_text(encoding="utf-8")
    assert '"/ai",' in nav
    assert '"/ai": "/chat"' in nav


def test_the_editor_puts_the_block_id_in_the_dom():
    """🔴 인용이 문단까지 가려면 앵커가 DOM 에 있어야 한다 (S10 Exit).

    `rendered: false` 로 되돌아가면 인용은 문서 맨 위까지만 데려간다 — 오류는 안 난다.
    """
    editor = (ROOT / "frontend" / "src" / "ui" / "BlockEditor.jsx").read_text(encoding="utf-8")
    assert '"data-block-id"' in editor
    doc = (ROOT / "frontend" / "src" / "screens" / "KnowledgeDoc.jsx").read_text(encoding="utf-8")
    assert 'params.get("block")' in doc
