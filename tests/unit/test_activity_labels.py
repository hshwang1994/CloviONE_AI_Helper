"""내 활동 피드가 **모든 감사 유형에 한국어 이름을 갖고 있는지** 소스에서 훑어 확인한다.

왜 이 테스트가 있는가: 실제 캡처에서 활동 피드에 목적어 없이 **"만듦"** 이라고만 적힌 줄이
여러 개 있었다. `department.create` 의 `department` 가 라벨 표에 없어서 명사가 비었던 것이다.
사람이 화면을 볼 때까지 아무도 몰랐고, 새 감사 유형이 생길 때마다 같은 일이 반복된다.

그래서 코드가 실제로 쓰는 `object_type=` 값을 소스에서 뽑아 표와 대조한다. grep 으로 잡히지
않는 변수 형태(`object_type=kind`, `OBJECT_TYPE = "..."`)는 그 값의 출처를 아래에 적어 두고
함께 검사한다 — 새 변수가 생기면 이 목록도 함께 늘려야 한다는 뜻이고, 그 사실 자체가
`describe_action` 의 계약이다.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.profiles.activity import OBJECT_LABELS, describe_action, object_particle

pytestmark = pytest.mark.unit

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "app"

_LITERAL = re.compile(r'object_type="([a-z_]+)"')

# grep 으로 안 보이는 값들 — 각각 어디서 오는지 함께 적는다.
DYNAMIC_OBJECT_TYPES = {
    "department": "app/org/router.py audit_type=",
    "job_title": "app/org/router.py audit_type=",
    "prompt": "app/prompts/router.py object_type=kind",
    "policy": "app/prompts/router.py object_type=kind",
    "app_setting": "app/settings/service.py OBJECT_TYPE",
    "workflow": "app/workflows/service.py OBJECT_TYPE",
    "integration": "app/integrations/service.py OBJECT_TYPE",
    "runner": "app/runners/service.py OBJECT_TYPE",
    # app/trash/router.py 는 f"notion_{item_type}" 로 만든다(notion_task / notion_document).
    "notion_task": "app/trash/router.py f-string",
    "notion_document": "app/trash/router.py f-string",
}


def _literal_object_types() -> set[str]:
    found: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        found.update(_LITERAL.findall(path.read_text(encoding="utf-8")))
    return found


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
    assert describe_action("ticket.update", "notion_task") == "티켓을 고침"
    assert describe_action("department.create", "department") == "부서를 만듦"
    assert describe_action("user.login", "user") == "로그인했습니다"


def test_unknown_action_keeps_the_original_text():
    """모르는 활동을 '알 수 없는 활동'으로 뭉개면 내가 한 일인데 무엇인지 알 수 없다."""
    assert describe_action("weird.thing", "nope") == "weird.thing"
    # 동사만 아는 경우에도 원문을 함께 남긴다(예전엔 "만듦" 한 단어만 나왔다).
    assert describe_action("mystery.create", "unknown_type") == "만듦 (mystery.create)"
