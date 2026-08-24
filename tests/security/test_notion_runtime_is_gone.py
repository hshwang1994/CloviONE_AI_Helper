"""노션으로 돌아가는 **쓰기 경로가 존재하지 않는다** (S15).

## 왜 「껐다」가 아니라 「없다」여야 하는가

컷오버 당일 배치 워커는 미러 틱이 등록된 채로 떴다. 그 틱들이 노션을 끌어와 `tickets` ·
`document_cache` · `projects` 에 쓰기 시작했는데, 그 셋은 그날부터 **정본**이었다. 설정으로
끄는 것으로는 안 멈췄다 — 데이터베이스의 값은 비웠지만 환경 파일에 데이터베이스 id 가
남아 있었고, 환경 파일이 이겼다. 그때는 잃은 것이 없었지만, 같은 사고가 다시 나면 사람이
포털에서 고친 내용 위로 옛 워크스페이스의 값이 덮인다. 되돌릴 방법도 없다.

그래서 이 파일은 설정을 보지 않는다. **경로 자체가 없다**는 것만 본다: 눌러서 동기화를
시작하던 버튼의 주소, 그 값을 정하던 관리 화면과 설정 키, 그리고 그것들을 부르던 모듈이
전부 없어야 한다.

## 지운 시험이 지키던 것을 여기서 마저 지킨다

아래 세 파일은 사라진 기능만 시험하고 있었다. 「그 기능이 되는가」는 지울 수 있어도
「그 기능이 없는가」는 누군가 지켜야 하고, 그 자리가 여기다.

qa-contract-replaced-by: tests/integration/test_notion_console.py
qa-contract-replaced-by: tests/integration/test_ticket_sync_trigger.py
qa-contract-replaced-by: tests/integration/test_docs_db_unset.py
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.core.allowlist import AllowlistRegistry, URLNotAllowedError

pytestmark = pytest.mark.security

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "app"

# 런타임에서 사라진 모듈. 이관 도구(`app/migration`, `app/cli`)는 여기 없다 — 그쪽은 옛
# 데이터를 한 번 읽어 오는 별개의 경로이고 허용 목록도 따로 쓴다.
REMOVED_MODULES = (
    "app.notion_console",
    "app.tickets.sync",
    "app.tickets.notion_write",
    "app.tickets.repository_notion",
    "app.team_docs.sync",
    "app.team_docs.notion_docs",
    "app.team_docs.repository_notion",
    "app.projects.sync",
    "app.projects.notion_source",
    "app.projects.notion_write",
    "app.reports.notion_source",
)

# 사라진 HTTP 표면. `(method, path)` 이고, 판정은 **404 나 405** 다 — 권한으로 막힌
# 401/403 은 「라우트가 아직 있다」는 뜻이라 통과시키면 안 된다.
REMOVED_ROUTES = (
    ("GET", "/api/admin/notion"),
    ("POST", "/api/admin/notion/test"),
    ("POST", "/api/admin/notion/token"),
    ("POST", "/api/admin/notion/databases"),
    ("POST", "/api/tickets/sync"),
    ("POST", "/api/team-docs/sync"),
)

# 사라진 설정 키. 값이 남아 있으면 「환경 파일이 이긴다」 사고가 그대로 되돌아온다.
REMOVED_SETTING_KEYS = (
    "notion_tasks_database_id",
    "notion_documents_database_id",
    "notion_sprint_database_id",
    "notion_docs_sync_interval_seconds",
    "notion_tickets_sync_interval_seconds",
    "notion_projects_sync_interval_seconds",
)


def test_the_removed_modules_cannot_be_imported():
    """되살아난 파일 하나가 정본 표에 다시 쓰기 시작하는 것을 여기서 막는다."""
    import importlib

    for name in REMOVED_MODULES:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(name)


def test_nothing_in_the_runtime_imports_them():
    """정적 — import 문 자체를 본다. 지연 import 도 AST 에는 남는다.

    실행으로만 확인하면 어느 분기 안에 숨은 import 는 그 분기를 안 지나는 시험에서
    조용히 통과한다.
    """
    offenders: list[str] = []
    scanned = 0
    for path in APP.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("app/migration/", "app/cli/")):
            continue
        scanned += 1
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if any(name == bad or name.startswith(bad + ".") for bad in REMOVED_MODULES):
                    offenders.append(f"{rel}: {name}")
    assert offenders == [], offenders
    # 검사기 자기검증: 표본이 0이면 「위반이 없다」와 「아무것도 안 봤다」가 같아진다.
    assert scanned > 50, f"훑은 파일이 {scanned}개뿐이다 — 검사가 헛돌고 있다"


def test_the_removed_module_files_are_not_on_disk():
    """반례를 겸한다 — 위 두 시험이 「파일이 있는데 못 찾는」 상태를 통과시키지 않는다."""
    for name in REMOVED_MODULES:
        rel = name.replace(".", "/")
        assert not (ROOT / f"{rel}.py").exists(), f"{rel}.py 가 아직 있다"
        assert not (ROOT / rel / "__init__.py").exists(), f"{rel}/ 가 아직 있다"


@pytest.mark.parametrize(("method", "path"), REMOVED_ROUTES)
def test_the_removed_routes_are_not_served(client, login_as, method, path):
    """가장 센 권한으로 눌러도 없다. **401/403 은 통과가 아니다** — 그건 라우트가 살아 있고
    권한만 막았다는 뜻이고, 권한 설정 한 줄이면 다시 열린다."""
    csrf = login_as("system_admin")
    response = client.request(method, path, headers={"X-CSRF-Token": csrf}, json={})
    assert response.status_code in (404, 405), (
        f"{method} {path} 가 아직 살아 있다: {response.status_code} {response.text[:200]}"
    )


def test_a_route_that_should_exist_still_answers(client, login_as):
    """**반례** — 위 검사가 「전부 404 인 세계」에서 초록을 찍는 것이 아니다.

    로그인이 안 됐거나 앱이 반쯤 떠 있으면 모든 주소가 404 처럼 보인다. 살아 있어야 하는
    주소 하나가 200 을 주는 것을 같은 세션에서 확인한다.
    """
    login_as("system_admin")
    assert client.get("/api/admin/settings").status_code == 200


def test_the_removed_setting_keys_are_neither_listed_nor_writable(client, login_as):
    """관리 콘솔이 그 값을 더는 보여 주지도, 받지도 않는다.

    돌지 않는 동기화의 값을 저장할 수 있게 두면 관리자는 저장 성공을 보고 무언가 달라졌다고
    믿는다. 그 거짓말은 다음에 진짜로 안 도는 것을 조사할 때 시간을 통째로 태운다.
    """
    csrf = login_as("system_admin")
    listed = client.get("/api/admin/settings").json()["settings"]
    for key in REMOVED_SETTING_KEYS:
        assert key not in listed, f"사라진 설정이 관리 콘솔 목록에 남아 있다: {key}"
        r = client.put(
            f"/api/admin/settings/{key}",
            json={"value": "a" * 32},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code >= 400, f"사라진 설정 키를 저장할 수 있다: {key}"


def test_the_runtime_allowlist_refuses_notion_at_the_gate():
    """설정 파일의 목록만 보지 않고 **관문이 실제로 거절하는지** 본다.

    `tests/security/test_migration_boundaries.py` 는 JSON 의 호스트 집합을 못박는다. 그
    집합이 맞아도 검사기가 안 부르면 아무 소용이 없으므로, 여기서는 같은 사실을 실행으로
    확인한다. 이관 관문은 반대로 통과해야 한다 — 통과하지 않으면 재설치가 막힌다.
    """
    registry = AllowlistRegistry(ROOT / "config")
    with pytest.raises(URLNotAllowedError):
        registry.get("services").check("https://api.notion.com/v1/pages")
    registry.get("migration").check("https://api.notion.com/v1/pages")
