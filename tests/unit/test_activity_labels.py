"""내 활동 피드가 **모든 감사 유형에 한국어 이름을 갖고 있는지** 소스에서 훑어 확인한다.

왜 이 테스트가 있는가: 실제 캡처에서 활동 피드에 목적어 없이 **"만듦"** 이라고만 적힌 줄이
여러 개 있었다. `department.create` 의 `department` 가 라벨 표에 없어서 명사가 비었던 것이다.
사람이 화면을 볼 때까지 아무도 몰랐고, 새 감사 유형이 생길 때마다 같은 일이 반복된다.

그래서 코드가 실제로 쓰는 `object_type=` 값을 소스에서 뽑아 표와 대조한다. grep 으로 잡히지
않는 변수 형태(`object_type=kind`, `OBJECT_TYPE = "..."`)는 그 값의 출처를 아래에 적어 두고
함께 검사한다 — 새 변수가 생기면 이 목록도 함께 늘려야 한다는 뜻이고, 그 사실 자체가
`describe_action` 의 계약이다.

qa-contract-change: 프롬프트와 정책 라우터는 `object_type=kind` 로 복수형("prompts", "policies")을 남기는데 이 목록은
단수형을 적고 있었다. 그래서 표의 단수형 키와 목록이 서로를 맞춰 주며 통과했고, 실제 활동 피드에서는 두 유형의 명사가
비었다. 기본 제공 프롬프트 복사 경로가 같은 값을 리터럴로 쓰면서 드러났다. 목록을 실제 값으로 고친다.

qa-contract-change: 동사는 동사표(`ux-writing-verb-table`)의 낱말로 쓴다 — 「만들었습니다 · 고쳤습니다 · 지웠습니다」가
「추가했습니다 · 수정했습니다 · 삭제했습니다」가 됐다(D-587). 그리고 표가 대상과 동사를 이어 붙이는 규칙만 보던 것을
넘어, 서버의 감사 호출 **전부**를 이 함수에 통과시켜 원문 키(`mail.test_send`)가 남지 않는지 본다. 화면 대장에서
내 활동과 감사 로그의 187개 동작 중 101개가 원문이나 「대상: 키」로 나온 것이 드러났다(r23).
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import re

import pytest

from app.profiles.activity import OBJECT_LABELS, describe_action, object_particle

pytestmark = pytest.mark.unit

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "app"

# **감사 기록 호출만** 본다. `object_type=` 이라는 같은 이름의 인자를 usage_events
# (`record_usage`)도 받는데, 그쪽 값은 활동 피드에 절대 닿지 않는다 — 문자열 grep 으로
# 훑었더니 `record_usage(object_type="ai", ...)` 가 걸려 없는 결함을 보고했다.
AUDIT_CALLS = ("record_audit", "record_audit_from_request")

# grep 으로 안 보이는 값들 — 각각 어디서 오는지 함께 적는다.
DYNAMIC_OBJECT_TYPES = {
    "department": "app/org/router.py audit_type=",
    "job_title": "app/org/router.py audit_type=",
    "prompts": "app/prompts/router.py object_type=kind",
    "policies": "app/prompts/router.py object_type=kind",
    "app_setting": "app/settings/service.py OBJECT_TYPE",
    "integration": "app/integrations/service.py OBJECT_TYPE",
    # app/trash/router.py 는 f"notion_{item_type}" 로 만든다(notion_task / notion_document).
    "notion_task": "app/trash/router.py f-string",
    "notion_document": "app/trash/router.py f-string",
}


def _callee_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _literal_object_types() -> set[str]:
    """감사 기록 호출에 **문자열 리터럴로** 넘어가는 object_type 전부."""
    found: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _callee_name(node.func) not in AUDIT_CALLS:
                continue
            for kw in node.keywords:
                if kw.arg == "object_type" and isinstance(kw.value, ast.Constant):
                    if isinstance(kw.value.value, str):
                        found.add(kw.value.value)
    return found


# 원문으로 남아도 되는 낱말 — 사람이 읽는 제품 이름과 약어다.
ALLOWED_LATIN = r"(?<![A-Za-z])(?:AI|CLI|CSV|DKIM|DNS|TLS|SMTP|Notion|ChatGPT)(?![A-Za-z])"


def _module_constant(path: pathlib.Path, name: str) -> str | None:
    """`object_type=OBJECT_TYPE` 처럼 이름으로 넘긴 값을 그 모듈에서 읽는다."""
    rel = path.relative_to(APP_DIR.parent).with_suffix("")
    try:
        module = importlib.import_module(".".join(rel.parts))
    except Exception:  # noqa: BLE001 — 읽지 못하면 아래 표로 넘어간다
        return None
    value = getattr(module, name, None)
    return value if isinstance(value, str) else None


def _audit_actions() -> list[tuple[str, str, list[str | None]]]:
    """감사 호출마다 (파일, 동작, 그 줄이 남길 수 있는 대상 유형들)."""
    found = []
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(APP_DIR.parent).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _callee_name(node.func) not in AUDIT_CALLS:
                continue
            kw = {k.arg: k.value for k in node.keywords}
            action = kw.get("action")
            if not (isinstance(action, ast.Constant) and isinstance(action.value, str)):
                continue
            obj = kw.get("object_type")
            types: list[str | None] = []
            if isinstance(obj, ast.Constant) and isinstance(obj.value, str):
                types = [obj.value]
            elif isinstance(obj, ast.Name):
                value = _module_constant(path, obj.id)
                if value:
                    types = [value]
            if not types:
                types = [v for v, where in DYNAMIC_OBJECT_TYPES.items() if where.startswith(rel)] or [None]
            found.append((rel, action.value, types))
    return found


def test_every_audit_action_reads_as_a_korean_sentence():
    """내 활동과 감사 로그가 동작 키를 그대로 보이지 않는다.

    「대상 + 동사」로 이을 수 없는 동작(목적어가 겹치거나 동사가 표에 없다)은 `ACTION_SENTENCES` 가 통문장을 든다.
    빠지면 `메일 발송: mail.test_send` · `수정했습니다 (setting.update)` 같은 줄이 사용자 화면에 선다.
    """
    actions = _audit_actions()
    assert len(actions) > 150, f"감사 호출을 거의 못 찾았다({len(actions)}건) — 훑는 방법이 낡았다"
    bad = []
    for rel, action, types in actions:
        for object_type in types:
            text = describe_action(action, object_type)
            if re.search(r"[A-Za-z]", re.sub(ALLOWED_LATIN, "", text)) or not text.endswith("습니다"):
                bad.append(f"{rel}: {action} ({object_type}) -> {text}")
    assert not bad, (
        "내 활동에 원문 키가 보이는 감사 동작이 있다. app/profiles/activity.py 의 ACTION_SENTENCES 에 문장을\n"
        "더하거나, 대상 이름(OBJECT_LABELS)과 동사(VERB_LABELS)를 더하라:\n  " + "\n  ".join(sorted(set(bad)))
    )


def test_no_verb_label_is_a_sentence_fragment():
    """조각 문장이 다시 들어오지 못하게 한다 — 이 표는 술어를 든다."""
    from app.profiles.activity import VERB_LABELS

    bad = sorted(v for v in VERB_LABELS.values() if not v.endswith("습니다"))
    assert not bad, (
        "내 활동 피드의 동사는 완결형이어야 한다(CLAUDE.md 한국어 규칙). 조각 문장:\n  "
        + "\n  ".join(bad)
    )


def test_every_audit_object_type_has_a_korean_label():
    used = _literal_object_types() | set(DYNAMIC_OBJECT_TYPES)
    missing = sorted(used - set(OBJECT_LABELS))
    assert not missing, (
        "내 활동 피드가 이름을 모르는 감사 대상이 있다 — 그 줄은 목적어 없이 '만듦' 처럼\n"
        "보인다. app/profiles/activity.py 의 OBJECT_LABELS 에 추가하라:\n  "
        + "\n  ".join(missing)
    )


def test_dynamic_sources_still_exist():
    """출처 주석이 낡지 않게 — 파일이 사라지면 이 목록도 손봐야 한다."""
    for value, where in DYNAMIC_OBJECT_TYPES.items():
        path = APP_DIR.parent / where.split()[0]
        assert path.exists(), f"{value} 의 출처로 적힌 {where} 가 더는 없다"


@pytest.mark.parametrize("word,expected", [
    ("티켓", "을"), ("문서", "를"), ("채팅방", "을"), ("계정", "을"),
    ("부서", "를"), ("러너", "를"), ("Notion 연결", "을"), ("job", "를"),
])
def test_object_particle_matches_korean_final_consonant(word, expected):
    assert object_particle(word) == expected


def test_known_action_reads_as_a_sentence():
    """한 피드가 **한 말투**로 말한다 (S19).

    예전에는 표 규칙이 명사형("티켓을 고침")이고 통문장 표가 완결형("로그인했습니다")이라,
    같은 화면에 두 문체가 섞여 나왔다. 둘 다 완결형이다.
    """
    assert describe_action("ticket.update", "notion_task") == "티켓을 수정했습니다"
    assert describe_action("department.create", "department") == "부서를 추가했습니다"
    assert describe_action("board_post.create", "board_post") == "게시글을 추가했습니다"
    assert describe_action("mail.test_send", "mail_delivery") == "시험 메일을 보냈습니다"
    assert describe_action("user.login", "user") == "로그인했습니다"


def test_unknown_action_keeps_the_original_text():
    """모르는 활동을 '알 수 없는 활동'으로 뭉개면 내가 한 일인데 무엇인지 알 수 없다."""
    assert describe_action("weird.thing", "nope") == "weird.thing"
    # 동사만 아는 경우에도 원문을 함께 남긴다(예전엔 동사 한 마디만 나왔다).
    assert describe_action("mystery.create", "unknown_type") == "추가했습니다 (mystery.create)"
