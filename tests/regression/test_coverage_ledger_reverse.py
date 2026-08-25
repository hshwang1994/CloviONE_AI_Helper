"""원장이 **없는 화면을 들고 있는가** — C1c 를 양방향으로 못 박는다 (S18).

Gate 의 C1 은 한 방향만 봤다: *소스에 있는 화면이 커버리지에 있는가.* 그 방향은 「새 화면을
등록 안 했다」를 잡지만, 반대 — *커버리지가 주장하는 화면이 소스에 아직 있는가* — 은 아무도
안 봤다. 그래서 S18 이 원장에서 **지워진 화면 셋**을 찾았다(설정 '연동' 탭 · `/notion-console` ·
`/team-docs/:id`). 그중 하나는 W8 소유라, 다음 회차가 **열리지도 않는 화면의 Flow 11개**를
감사 대상으로 받게 돼 있었다.

여기서 검사하는 것은 제품이 아니라 **검사 자체**다. 새 조건이 「통과한다」는 것만으로는
아무것도 증명되지 않는다 — 위반을 실제로 **드는지**(Known Bad)와 정상을 **안 드는지**
(Known Good)를 함께 본다. S17 이 잉크 비율에서 밟은 실패가 이 형태였다: 통과하지만 잘못된
표본을 재던 검사.
"""

from __future__ import annotations

import scripts.check_ui_renewal_coverage as gate


def _run(surfaces, *, literal=None, navigate=None, tab_bodies=None,
         harness_paths=None, harness_surface_ids=None) -> gate.Report:
    rep = gate.Report()
    gate.c1c_coverage_vs_source(
        rep, surfaces,
        literal or {},
        navigate or {},
        tab_bodies or set(),
        harness_paths or set(),
        harness_surface_ids or set(),
    )
    return rep


def _fails(rep: gate.Report) -> list[str]:
    return [str(f) for f in rep.fails]


LIVE_FILE = "scripts/check_ui_renewal_coverage.py"   # 이 저장소에 확실히 있는 파일
DEAD_FILE = "frontend/src/screens/NotionConsole.jsx"  # S14 가 지운 파일


def test_known_good_live_screen_passes():
    """살아 있는 화면은 안 든다."""
    rep = _run(
        [{"id": "live", "kind": "route", "route": "/projects", "component": LIVE_FILE,
          "status": "DONE"}],
        literal={"/projects": {}},
    )
    assert _fails(rep) == []


def test_known_bad_component_file_is_gone():
    """그리는 파일이 없어졌으면 든다 — `admin_settings__integration` 의 실제 형태다."""
    rep = _run([{"id": "ghost", "kind": "route", "route": "/x", "component": DEAD_FILE,
                 "status": "NOT_AUDITED"}])
    assert any("없는 파일" in f for f in _fails(rep)), _fails(rep)


def test_known_bad_tab_body_is_gone():
    """소스의 탭 목록에 없는 탭 본문은 든다."""
    rep = _run(
        [{"id": "ghost_tab", "kind": "tab", "route": "/settings?tab=integration",
          "component": LIVE_FILE, "status": "NOT_AUDITED"}],
        tab_bodies={"/settings?tab=policy", "/settings?tab=os", "/settings?tab=ai"},
    )
    assert any("탭 본문" in f for f in _fails(rep)), _fails(rep)


def test_known_good_tab_body_that_exists():
    rep = _run(
        [{"id": "ok_tab", "kind": "tab", "route": "/settings?tab=os",
          "component": LIVE_FILE, "status": "DONE"}],
        tab_bodies={"/settings?tab=os"},
    )
    assert _fails(rep) == []


def test_known_bad_redirect_is_gone():
    """`<Navigate>` 가 없어진 별칭은 든다 — `/notion-console` 의 실제 형태다."""
    rep = _run(
        [{"id": "ghost_alias", "kind": "state_variant", "route": "/notion-console",
          "alias_of": "admin_settings", "component": LIVE_FILE, "status": "NOT_AUDITED"}],
        navigate={"/system": "/settings?tab=os"},
    )
    assert any("리다이렉트" in f for f in _fails(rep)), _fails(rep)


def test_known_good_redirect_that_exists():
    rep = _run(
        [{"id": "ok_alias", "kind": "state_variant", "route": "/system",
          "alias_of": "admin_settings", "component": LIVE_FILE, "status": "NOT_AUDITED"}],
        navigate={"/system": "/settings?tab=os"},
    )
    assert _fails(rep) == []


def test_retired_screen_is_silent():
    """RETIRED 로 적으면 안 든다 — 그것이 이 조건이 요구하는 정정이다."""
    rep = _run(
        [{"id": "retired", "kind": "tab", "route": "/settings?tab=integration",
          "component": DEAD_FILE, "status": "RETIRED"}],
        tab_bodies={"/settings?tab=policy"},
    )
    assert _fails(rep) == []


def test_retired_but_still_in_source_is_caught():
    """**반대편도 막는다.** 되살린 화면을 RETIRED 로 둔 채면 그 화면은 검사 밖으로 나간다."""
    rep = _run(
        [{"id": "revived", "kind": "route", "route": "/projects", "component": LIVE_FILE,
          "status": "RETIRED"}],
        literal={"/projects": {}},
    )
    assert any("RETIRED 인데 소스에 아직 있다" in f for f in _fails(rep)), _fails(rep)


def test_retired_but_the_harness_still_captures_it():
    """하네스가 계속 찍고 있으면 **캡처에 다른 화면이 그 이름으로 담긴다** — 그것도 든다.

    설정 화면은 모르는 탭 키를 첫 탭으로 되돌리므로, 없어진 `?tab=integration` 을 찍으면
    '시스템 정책' 이 '연동' 이라는 이름으로 남는다. 가장 조용한 종류의 거짓이다.
    """
    rep = _run(
        [{"id": "admin_settings__integration", "kind": "tab",
          "route": "/settings?tab=integration", "component": DEAD_FILE, "status": "RETIRED"}],
        tab_bodies={"/settings?tab=policy"},
        harness_surface_ids={"admin_settings__integration"},
    )
    assert any("RETIRED 인데 소스에 아직 있다" in f for f in _fails(rep)), _fails(rep)


def test_retired_row_whose_route_a_live_row_took_over():
    """한 주소를 두 행이 주장하면, 옛 행을 RETIRED 로 적는 것이 **정확히 맞는 정정**이다.

    `/team-docs/:pageId` 가 그렇다 — 지운 `TeamDoc.jsx` 를 가리키던 옛 행과 지금
    `LegacyDocRedirect` 를 가리키는 행이 같은 주소다. 주소만 보면 「RETIRED 인데 소스에
    있다」로 되받게 되고, 그러면 고칠 방법이 없어진다.
    """
    rep = _run(
        [
            {"id": "user_team-docs-id", "kind": "route", "route": "/team-docs/:id",
             "component": "frontend/src/screens/TeamDoc.jsx", "status": "RETIRED"},
            {"id": "user_legacy-doc-redirect", "kind": "route", "route": "/team-docs/:pageId",
             "component": "frontend/src/screens/LegacyDocRedirect.jsx", "status": "NOT_AUDITED"},
        ],
        literal={"/team-docs/:id": {}},
        harness_paths={"/team-docs/:id"},
        harness_surface_ids={"user_legacy-doc-redirect"},
    )
    assert _fails(rep) == []


def test_component_path_strips_annotation():
    """`component` 칸은 파일 + 위치를 함께 적기도 한다 — 괄호 앞까지가 파일이다."""
    assert gate.component_path(
        {"component": 'frontend/src/app/UserRoutes.jsx (<Navigate to="/knowledge">)'}
    ) == "frontend/src/app/UserRoutes.jsx"
    assert gate.component_path({"component": "(전 화면)"}) == ""
    assert gate.component_path({}) == ""


def test_real_ledger_has_no_ghost_left():
    """그리고 **지금 저장소의 진짜 원장**에 유령이 남아 있지 않다."""
    import json
    import os

    with open(os.path.join(gate.ROOT, "docs", "ui-renewal", "ROUTE_COVERAGE.json"),
              encoding="utf-8") as fh:
        cov = json.load(fh)
    user = gate.read_jsx_routes(gate.USER_ROUTES_JSX)
    admin = gate.read_jsx_routes(gate.ADMIN_ROUTES_JSX)
    literal, navigate = {}, {}
    for in_file in (user, admin):
        for path, meta in in_file.items():
            if path == "*":
                continue
            (navigate if meta["navigate_to"] else literal)[path] = meta
    groups = gate.read_tab_groups()
    tab_bodies = {"%s?tab=%s" % (g["path"], t) for g in groups for t in g["tabs"]}
    tab_bodies |= {"/settings?tab=%s" % t for t in gate.read_settings_tabs()}

    from scripts.ui_qa.routes import ALIAS_ROUTES, ALL_ROUTES

    harness_paths = {gate._ROUTE_PARAM.sub(":id", r.source_path or r.hash_template or r.hash_path)
                     for r in ALL_ROUTES}
    harness_paths |= {gate._ROUTE_PARAM.sub(":id", r.hash_path) for r in ALIAS_ROUTES}
    harness_ids = {r.surface_id for r in ALL_ROUTES} | {r.surface_id for r in ALIAS_ROUTES}

    rep = _run(cov["surfaces"], literal=literal, navigate=navigate, tab_bodies=tab_bodies,
               harness_paths=harness_paths, harness_surface_ids=harness_ids)
    assert _fails(rep) == []


# ─────────────────────────────────────────────────────────────────────────────
# C11 — 서버를 안 부르는 Flow 의 PASS 는 무엇을 요구하는가 (S18)
# ─────────────────────────────────────────────────────────────────────────────
#
# 이 조건은 «모든 Flow 가 서버를 부른다» 를 전제로 쓰여 있었다. 모달 열기·탭 전환·필수값
# 검증은 **안 부르는 것이 정답**이라, 그 전제 아래에서는 답이 둘뿐이었다: 사슬을 지어내거나
# 영원히 `IN_PROGRESS` 로 두거나. W2~W4 가 후자를 골랐고 그래서 `kit_primitives` 다섯은
# 지금도 그 상태다. S18 은 **선언**을 요구하는 쪽으로 바꿨다 — 아래가 그 양방향이다.


def _flow_report(surface_id, flow) -> gate.Report:
    rep = gate.Report()
    gate.c11_c14_functional(
        rep,
        [{"id": surface_id, "kind": "route", "wave": "W8", "status": "DONE"}],
        {"categories": ["modal_action", "read"],
         "surfaces": [{"surface": surface_id, "inventory_status": "INVENTORIED",
                       "flows": [flow]}]},
        {surface_id},
        "wave",
    )
    return rep


CLIENT_CHAIN = {"ui_action": "«수정» 을 누른다", "frontend_state": "open=true",
                "rendered": "대화상자 «티켓 수정»"}
SERVER_CHAIN = {"api_request": "GET /api/x", "backend_query": "list_x (GET /api/x)",
                "api_response": "HTTP 200", "rendered": "표 3행"}
WHY = "모달을 여는 동작이라 서버를 부르지 않는다 — 하네스가 요청 0건을 관측했다."


def test_server_free_pass_needs_the_client_chain():
    rep = _flow_report("user_me", {
        "id": "FF-9001", "category": "modal_action", "name": "모달", "exists": True,
        "status": "PASS", "server_free": WHY, "chain": CLIENT_CHAIN,
        "evidence": ["ev:qa_run:dist/ui-qa/w8-pilot-e2e/flows.json"],
        "expected": {"source": "known-data"},
    })
    assert _fails(rep) == []


def test_server_free_without_a_reason_is_caught():
    """**사유가 곧 대가다.** 한 줄도 안 적고 서버 칸만 비우는 길은 없다."""
    rep = _flow_report("user_me", {
        "id": "FF-9002", "category": "modal_action", "name": "모달", "exists": True,
        "status": "PASS", "server_free": True, "chain": CLIENT_CHAIN,
        "evidence": ["ev:qa_run:x"], "expected": {"source": "known-data"},
    })
    assert any("server_free 사유가 없다" in f for f in _fails(rep)), _fails(rep)


def test_server_free_that_also_fills_server_columns_is_a_contradiction():
    rep = _flow_report("user_me", {
        "id": "FF-9003", "category": "modal_action", "name": "모달", "exists": True,
        "status": "PASS", "server_free": WHY, "chain": {**CLIENT_CHAIN, **SERVER_CHAIN},
        "evidence": ["ev:qa_run:x"], "expected": {"source": "known-data"},
    })
    assert any("서버 칸이 채워져 있다" in f for f in _fails(rep)), _fails(rep)


def test_server_free_with_an_empty_client_chain_is_caught():
    rep = _flow_report("user_me", {
        "id": "FF-9004", "category": "modal_action", "name": "모달", "exists": True,
        "status": "PASS", "server_free": WHY, "chain": {"ui_action": "누른다"},
        "evidence": ["ev:qa_run:x"], "expected": {"source": "known-data"},
    })
    assert any("화면 사슬이 비어 있다" in f for f in _fails(rep)), _fails(rep)


def test_a_server_flow_still_needs_the_full_chain():
    """**느슨해지지 않았다.** 선언이 없으면 예전 규칙 그대로다."""
    rep = _flow_report("user_me", {
        "id": "FF-9005", "category": "read", "name": "조회", "exists": True,
        "status": "PASS", "chain": CLIENT_CHAIN,
        "evidence": ["ev:qa_run:x"], "expected": {"source": "known-data"},
    })
    assert any("사슬이 비어 있다" in f for f in _fails(rep)), _fails(rep)
