"""「실제 효과: 있음」이 사실인지 **코드로** 확인한다 — 죽은 스위치를 표시로만 관리하지 않는다.

## 무엇이 새어 나갔나 (2026-09-06 실측)

`document_automation_enabled` 는 저장소 전체에서 읽는 코드가 0인데(선언 두 곳뿐) 기능 플래그
화면의 '실제 효과' 열은 「있음」이라고 말했다. 그 값을 끈 뒤에도
`POST /api/knowledge/documents` 는 그대로 200 이었다. 사고 중에 문서 생성을 잠그려던 관리자는
막혔다고 믿고 다음 조치를 하지 않는다 — `app/core/feature_flags.py` 머리말이 스스로 사고
사례로 적어 둔 바로 그 부류다.

원인은 판정 방법이었다. 예전 `has_consumer` 는 설명 문자열에 `(소비자 없음)` 이 들어 있는지만
봤고, 그 표식은 사람이 손으로 붙인다 — **빠뜨리면 자동으로 「있음」이 된다.** 틀리는 방향이
안전한 쪽이 아니다.

## 이 파일이 하는 일

`app/` 를 AST 로 훑어 각 키 이름이 **선언 파일 밖의 코드 문자열로** 등장하는지 센다. 주석은
AST 에 없고 독스트링은 빼므로, 「이야기 속에만 있는 키」와 「진짜 읽는 키」가 갈린다. 그
결과와 `app/admin/feature_flags.py::_NO_CONSUMER_FLAGS` 가 어긋나면 빨간불이다 — 새 스위치를
소비자 없이 넣은 날에도, 소비자를 붙이고 목록에서 지우는 것을 잊은 날에도 걸린다.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 키를 **선언만** 하는 파일. 여기 등장하는 것은 소비가 아니다.
DECLARATION_FILES = frozenset(
    {
        "app/core/feature_flags.py",
        "app/settings/registry.py",
        "app/admin/feature_flags.py",
    }
)


def _code_strings(path: Path) -> set[str]:
    """이 파일의 문자열 리터럴 — **독스트링은 뺀다**.

    주석(`#`)은 AST 에 아예 없으므로 저절로 빠진다. 독스트링만 손으로 골라내면 남는 것은
    코드가 실제로 쓰는 문자열이다.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def _keys_read_by_app() -> set[str]:
    seen: set[str] = set()
    for path in sorted((PROJECT_ROOT / "app").rglob("*.py")):
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if rel in DECLARATION_FILES:
            continue
        seen |= _code_strings(path)
    return seen


def test_no_consumer_list_matches_what_the_code_actually_reads():
    from app.admin.feature_flags import _NO_CONSUMER_FLAGS
    from app.core.feature_flags import FLAG_REGISTRY

    read = _keys_read_by_app()
    dead = {name for name in FLAG_REGISTRY if name not in read}
    assert dead == set(_NO_CONSUMER_FLAGS), (
        "기능 플래그 목록과 실제 소비자가 어긋난다. 읽는 코드가 없는데 목록에 없는 키: "
        f"{sorted(dead - set(_NO_CONSUMER_FLAGS))} · 목록에 있는데 읽는 코드가 생긴 키: "
        f"{sorted(set(_NO_CONSUMER_FLAGS) - dead)}"
    )


def test_document_automation_enabled_is_still_a_switch_nothing_reads():
    """이 키가 죽어 있다는 사실 자체를 못박는다.

    설명(`app/settings/registry.py`)은 아직 「끄면 신규 문서 생성 요청이 거부됩니다」라고
    말한다. 그 문구를 고치든 게이트를 붙이든, **둘 중 하나를 하면 이 시험이 빨간불이 되어**
    이 파일과 화면의 판정을 같이 고치게 한다.
    """
    read = _keys_read_by_app()
    assert "document_automation_enabled" not in read
    # 반례: 같은 성격의 다른 스위치는 실제로 읽힌다 — 스캐너가 전부를 '없음'으로 보고
    # 있는 것이 아니다.
    assert "board_enabled" in read
    assert "maintenance_mode" in read


def test_screen_reports_effect_honestly(client, login_as):
    login_as("system_admin")
    body = client.get("/api/admin/feature-flags")
    assert body.status_code == 200, body.text
    rows = {row["name"]: row for row in body.json()["items"]}

    assert rows["document_automation_enabled"]["has_consumer"] is False
    assert rows["limited_service_actions_enabled"]["has_consumer"] is False
    # 반례 — 실제로 읽히는 스위치는 그대로 「있음」이다.
    assert rows["board_enabled"]["has_consumer"] is True
    assert rows["maintenance_mode"]["has_consumer"] is True
