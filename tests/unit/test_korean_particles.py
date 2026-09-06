"""조사는 한 자리에서 고른다 — 「을(를)」 같은 괄호 표기가 화면에 안 나가게.

2026-09-06 배포 환경(clovirassist.gooddi.lab)에서 관리자 폼의 필수 칸 오류가
「제목을(를) 입력하세요.」로 나오는 것을 실측했다. 주어가 데이터(칸 이름, 부서/직책
라벨, 문서 제목)라 문장을 손으로 적어 둘 수 없다는 이유로 두 조사를 나란히 적어 온
자리들이다. 그것은 한국어 문장이 아니라 미결정 상태를 화면에 그대로 내보낸 것이고,
CLAUDE.md §10 이 금지한다.

이 시험이 지키는 것은 둘이다.

1. 판정이 **하나**다. 이 저장소에는 같은 계산이 세 벌 있었고(`profiles/activity.py`,
   `auth/router.py`, `core/text.py`) 비한글 낱말에서 서로 **다른 답**을 냈다 —
   「job를」과 「job을」이 한 제품 안에 동시에 있었다. 이제 셋이 같은 함수를 본다.
2. 문구에 괄호 표기가 없다. 반례로 받침 있는 낱말과 없는 낱말을 함께 재지 않으면
   「항상 을」도 통과하고, 그러면 「부서를」이 아니라 「부서을」이 살아난다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.auth.router import _subject_particle
from app.core.text import (
    has_final_consonant,
    object_particle,
    subject_particle,
    topic_particle,
)
from app.profiles.activity import object_particle as activity_object_particle

APP_DIR = Path(__file__).resolve().parents[2] / "app"

#: 「을(를)」 「은(는)」 「이(가)」 「와(과)」 처럼 조사를 나란히 적은 자리.
BRACKETED = re.compile(r"[을은이와를가]\([를는가과을이]\)")


@pytest.mark.parametrize("word,expected", [
    ("제목", "을"), ("이름", "을"), ("직책", "을"), ("계정", "을"),
    ("부서", "를"), ("메모", "를"), ("대상자", "를"), ("주기", "를"),
    ("job", "를"), ("Cron", "를"), ("2026", "를"), ("", "를"),
])
def test_object_particle(word: str, expected: str) -> None:
    assert object_particle(word) == expected


@pytest.mark.parametrize("word,expected", [
    ("설정", "은"), ("기능 깃발", "은"), ("실행 일정", "은"),
    ("부서", "는"), ("프롬프트", "는"), ("Cron", "는"), ("", "는"),
])
def test_topic_particle(word: str, expected: str) -> None:
    assert topic_particle(word) == expected


@pytest.mark.parametrize("word,expected", [
    ("티켓", "이"), ("채팅방", "이"),
    ("담당자", "가"), ("문서", "가"), ("ClovirAssist", "가"), ("", "가"),
])
def test_subject_particle(word: str, expected: str) -> None:
    assert subject_particle(word) == expected


def test_three_particles_share_one_batchim_verdict() -> None:
    """세 조사가 같은 낱말에서 같은 받침 판정을 쓴다."""
    for word in ["제목", "부서", "티켓", "담당자", "job", "Cron", ""]:
        batchim = has_final_consonant(word)
        assert (object_particle(word) == "을") is batchim
        assert (topic_particle(word) == "은") is batchim
        assert (subject_particle(word) == "이") is batchim


def test_older_copies_now_answer_the_same() -> None:
    """옛 이름으로 부르던 두 자리가 같은 함수를 본다 — 비한글에서 갈리던 그 자리다."""
    for word in ["티켓", "부서", "job", "Cron", "ClovirAssist", ""]:
        assert activity_object_particle(word) == object_particle(word)
        assert _subject_particle(word) == subject_particle(word)


def test_no_bracketed_particle_reaches_a_user_string() -> None:
    """`app/` 의 **코드**(주석·문서화 문자열 밖)에 괄호 조사가 없다.

    주석과 문서화 문자열은 이 규칙을 설명하려고 그 표기를 인용한다 — 그것까지 막으면
    규칙을 적어 둘 자리가 없어진다. 판정은 「따옴표 안의 문자열 리터럴인가」로 한다.
    """
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("#", "*", '"""', "'''")):
                continue
            # 인용 부호(「」) 안은 규칙을 설명하는 산문이다.
            if "「" in stripped or "」" in stripped:
                continue
            if BRACKETED.search(stripped):
                offenders.append(f"{path.relative_to(APP_DIR.parent)}:{lineno}  {stripped}")
    assert offenders == [], "괄호 조사가 사용자 문구에 남아 있다:\n" + "\n".join(offenders)


def test_the_checker_would_catch_a_regression() -> None:
    """반례 — 검사 자체가 살아 있는가. 실제 결함 문구를 넣으면 잡혀야 한다."""
    assert BRACKETED.search('raise ValidationAppError(f"{label}은(는) 비울 수 없습니다.")')
    assert BRACKETED.search('f"{name} 을(를) 찾지 못했습니다."')
    assert not BRACKETED.search('f"{label}{topic_particle(label)} 비울 수 없습니다."')
