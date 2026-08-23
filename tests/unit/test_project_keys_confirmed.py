"""확정된 Project Key 20건이 **문서와 코드에서 같은가** (U11 · D-197 · D-243).

## 왜 이 시험이 있는가

Key 소유는 영구다(D-196). 한 줄을 틀리면 그 프로젝트의 티켓 전부가 다른 이름으로
불리고, `retired` 로 물러날 뿐 되돌릴 수 없다.

확정표가 **두 곳**에 있다: 사람이 읽는 `docs/platform/PROJECT_KEYS.md` 와 S13 이 읽는
`app/work/project_keys.py::CONFIRMED`. 둘이 갈라지면 「문서에는 SKH 인데 적용된 것은
SHK」 같은 상태가 되고, 그때 문서를 보고 확인한 사람은 아무 이상도 못 느낀다.

그래서 여기서 둘을 맞물어 둔다 — S5 가 권한 표에, S6 이 상태 어휘에 쓴 것과 같은 수법.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.work import keys as keys_mod
from app.work.project_keys import (
    BY_KEY,
    BY_NAME,
    CONFIRMED,
    CONFIRMED_ON,
    SUPERSEDED_NAMES,
    key_for_name,
)

pytestmark = pytest.mark.unit

DOC = (
    pathlib.Path(__file__).resolve().parents[2]
    / "docs" / "platform" / "PROJECT_KEYS.md"
)
# 확정표 한 줄: `| 3 | `PDX` | `이름` | 137 | 이유 |`
_ROW = re.compile(r"^\|\s*\d+\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|", re.M)


def _doc_rows() -> list[tuple[str, str]]:
    return _ROW.findall(DOC.read_text(encoding="utf-8"))


def test_the_detector_actually_reads_the_table():
    """**빈 표를 훑고 초록을 찍는 상태**가 아님을 먼저 보인다 (D-213).

    정규식이나 경로가 틀리면 0줄을 읽고 「어긋난 것이 없다」로 통과한다.
    """
    rows = _doc_rows()
    assert len(rows) == 20, f"문서에서 확정 20줄을 못 읽었다 — {len(rows)}줄 읽었다"


def test_document_and_code_hold_the_same_table():
    """문서와 코드가 **같은 20쌍**인가. 순서까지 같아야 한다.

    순서를 안 보면 두 줄이 서로 바뀐 상태가 통과한다 — 그 상태에서 적용하면 두
    프로젝트가 서로의 Key 를 가져간다.
    """
    assert _doc_rows() == [(key, name) for key, name in CONFIRMED], (
        "문서(`docs/platform/PROJECT_KEYS.md`)와 코드"
        "(`app/work/project_keys.py::CONFIRMED`)의 확정표가 다르다"
    )


def test_the_document_says_it_is_confirmed_on_the_same_day():
    text = DOC.read_text(encoding="utf-8")
    assert CONFIRMED_ON in text, (
        f"문서에 확정일 {CONFIRMED_ON} 이 없다 — 코드와 문서가 다른 확정을 말한다"
    )


# ── 규칙 (§5.2) ──────────────────────────────────────────────────────────────


def test_every_confirmed_key_obeys_the_rules():
    """확정된 Key 가 **제품의 규칙을 실제로 통과하는가.**

    사람이 지은 이름이라 규칙 밖 값이 섞일 수 있다. 적용하는 날 `claim()` 이 거절하면
    그 프로젝트만 조용히 빠진다.
    """
    for key, name in CONFIRMED:
        assert keys_mod.validate(key) == key, f"«{key}»({name}) 이 규칙을 어긴다"


def test_no_confirmed_key_collides_with_a_reserved_one():
    """`GIT` 을 가져가면 새 `GIT-142` 가 옛 `GIT-142` 와 같은 문자열이 된다 (D-196)."""
    clash = sorted(set(BY_KEY) & set(keys_mod.RESERVED_KEYS))
    assert not clash, f"예약어와 겹치는 확정 Key: {clash}"


def test_keys_and_names_are_both_unique():
    """Key 가 겹치면 두 프로젝트가 같은 이름을 갖고, 이름이 겹치면 어느 Key 인지 모른다."""
    assert len(BY_KEY) == len(CONFIRMED), "Key 가 겹친다"
    assert len(BY_NAME) == len(CONFIRMED), "프로젝트 이름이 겹친다"


def test_lookup_is_exact_and_does_not_guess():
    """비슷한 이름을 같다고 보지 않는다 — 그것이 U11 이 금지한 임의 배정이다.

    공백과 유니코드 합성만 다듬는다. 철자가 다르면 **못 찾는다**.
    """
    key, name = CONFIRMED[0]
    assert key_for_name(name) == key
    assert key_for_name(f"  {name}  ") == key, "앞뒤 공백은 같은 이름이다"
    assert key_for_name(name.replace(" ", "  ")) == key, "겹공백은 같은 이름이다"

    assert key_for_name(name + " 2차") is None, "덧붙은 이름을 같다고 봤다"
    assert key_for_name(name[:-1]) is None, "잘린 이름을 같다고 봤다"
    assert key_for_name("없는 프로젝트") is None
    assert key_for_name(None) is None


def test_the_rename_moved_names_and_left_keys_alone():
    """2026-08-23 에 소스가 이름을 바꿨다. **Key 는 안 바뀌었다** (S13).

    이 시험이 지키는 것은 이름 스무 개가 아니라 **Key 스무 개의 불변성**이다. 다음
    사람이 이름을 또 갈 때 Key 까지 함께 건드리면 그 프로젝트의 티켓 전부가 다른
    이름으로 불리고, 소유는 영구라 되돌릴 수 없다(D-196).
    """
    assert [key for key, _ in CONFIRMED] == [key for key, _ in SUPERSEDED_NAMES], (
        "Key 목록과 순서는 앞 판과 같아야 한다 — 이름만 갈았다"
    )
    # 14번은 잘린 채로 확정됐고 소스가 완성했다. 두 판이 다 남아 있어야 한다.
    assert BY_KEY["OKE"] == "현대모비스 [OKE KVM 윈도우 기능 개선]"
    assert dict(SUPERSEDED_NAMES)["OKE"] == "M. 현대모비스 [OKE KVM 윈도우 기능 개"


def test_no_name_survived_the_rename_unchanged():
    """앞 판과 지금 판에 **같은 문자열이 있으면** 그 줄은 안 바뀐 것이다.

    안 바뀐 줄이 섞여 있으면 「소스가 전부 바뀌었다」는 이 회차의 판단이 틀렸다는
    뜻이고, 그때는 바뀐 줄과 안 바뀐 줄을 구별해서 다시 확인해야 한다.
    """
    same = sorted(set(dict(CONFIRMED).values()) & set(dict(SUPERSEDED_NAMES).values()))
    assert not same, f"이름이 안 바뀐 줄이 있다: {same}"


def test_old_names_still_resolve_to_the_same_key():
    """옛 이름을 든 소스를 만나도 같은 Key 로 붙는다 — **추측이 아니라 기록 조회다.**"""
    for key, old_name in SUPERSEDED_NAMES:
        assert key_for_name(old_name) == key, f"옛 이름이 {key} 로 안 붙는다"
    # 그렇다고 아무 이름이나 붙지는 않는다.
    assert key_for_name("P. 없는 프로젝트") is None
