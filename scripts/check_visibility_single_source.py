"""목록·상세·Search 가 **같은 함수**로 가시성을 판정하는지 확인한다 (D-194 · S5 Exit).

## 왜 이 검사가 생겼는가

D-194 는 「넷이 정말 같은 함수를 부르는가」를 **도구가 봐야 한다**고 적었다. 근거는 W5 에서
`TicketFilterBar` 가 「순서는 C2 가 정한다」고 주석에 적고 39줄 뒤에서 그 순서를 어긴 일이다.
**「같은 규칙을 따른다」는 주석은 증거가 아니다.**

S5 이전 상태가 정확히 그랬다. 소속 판정은 `app/core/ownership.py` 를 함께 썼는데,

  * 목록·상세는 **파이썬 행 판정**(`scope_can_view`),
  * Search 는 **SQL 절**(`stored_ownership_clause`),
  * 열람 제한(SEC-10)은 **양쪽에 따로**(`doc_in_scope` 안 · `not_restricted_clause`)

라서 「같은 규칙」이라는 말이 절반만 사실이었다. 지금은 판정이 `app/authz/visibility.py`
한 곳이고, 이 검사는 그것이 **다시 갈라지지 않는지**를 본다.

## 규칙 둘

1. **소비자는 그 함수에 닿는다.** 아래 `CONSUMERS` 의 각 파일이 `app/authz/visibility.py`
   를 import 하고 그 입구 중 하나를 실제로 부른다.
2. **은퇴한 판정 부품이 되살아나지 않는다.** 옛 이름들이 `app/authz/visibility.py` 밖에서
   **정의**되면 그 순간 판정이 두 벌이 된다. 이름만 다르게 되살리는 것까지는 못 잡지만,
   되살리는 가장 흔한 방법이 「옛 함수를 그대로 다시 만드는 것」이다.

## 한계 (일부러 적어 둔다)

정적 검사다. **증명이 아니라 「생각조차 안 한 곳」을 잡는 그물**이다. 부르지만 결과를 안 쓰는
코드는 못 잡는다 — 그쪽은 `tests/security/test_visibility_two_renderers_agree.py` 와
음성 테스트가 본다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 콘솔이 cp949 면 한글 문장부호에서 죽는다 — 결과를 못 읽는 실패는 실패보다 나쁘다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "app/authz/visibility.py"

# 판정을 소비하는 자리. 값은 **무엇을 답하는 경로인가**이고, 실패 메시지에 그대로 실린다.
CONSUMERS: dict[str, str] = {
    "app/projects/repository.py": "프로젝트 목록·상세",
    "app/team_docs/service.py": "문서 목록·상세",
    "app/search/scoping.py": "Search",
    "app/tickets/service.py": "티켓(프로젝트 가시성 상속)",
    "app/knowledge/service.py": "지식 공간·문서(공간 가시성 상속)",
}

# `app/authz/visibility.py` 의 공개 입구. 하나라도 부르면 「그 함수에 닿았다」로 본다.
ENTRIES = (
    "effective_visibility_clause",
    "is_visible",
    "visible_project_ids",
    "visibility_context",
    "context_for_user",
    "users_who_can_view_project",
)

# S5 가 은퇴시킨 판정 부품. 이 이름으로 **다시 정의하면** 판정이 두 벌이 된다.
RETIRED = (
    "stored_ownership_clause",
    "project_scope_clause",
    "scope_can_view",
    "not_restricted_clause",
)

DEF_RE = re.compile(r"^\s*def\s+(\w+)\s*\(", re.M)
DOCSTRING_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')
COMMENT_RE = re.compile(r"#[^\n]*")


def code_only(text: str) -> str:
    """주석과 docstring 을 뺀 실행 코드만.

    이 저장소는 「왜」를 길게 적는 것이 규칙이라 함수 이름이 산문에 자주 나온다. 그대로 두면
    **설명만 하고 부르지 않는 코드**가 통과한다 — `check_scope_gates.py` 가 실제로 그렇게
    한 번 뚫렸다.
    """
    return COMMENT_RE.sub("", DOCSTRING_RE.sub("", text))


def check(read) -> tuple[list[str], int, int]:
    """`read(rel) -> str` 를 주면 (위반, 확인한 소비자 수, 훑은 파일 수)."""
    problems: list[str] = []

    for rel, what in CONSUMERS.items():
        src = code_only(read(rel))
        if "app.authz.visibility" not in src:
            problems.append(f"{rel}: {what} 가 {SOURCE} 를 import 하지 않는다")
            continue
        if not any(entry in src for entry in ENTRIES):
            problems.append(
                f"{rel}: {what} 가 {SOURCE} 를 import 만 하고 입구를 부르지 않는다 "
                f"(하나 이상 필요: {', '.join(ENTRIES)})"
            )

    scanned = 0
    for path in sorted((ROOT / "app").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel == SOURCE:
            continue
        scanned += 1
        defined = set(DEF_RE.findall(read(rel)))
        for name in RETIRED:
            if name in defined:
                problems.append(
                    f"{rel}: 은퇴한 판정 부품 `{name}` 이 다시 정의됐다 — "
                    f"가시성 판정은 {SOURCE} 한 곳이다 (D-194)"
                )
    return problems, len(CONSUMERS), scanned


def _read_file(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def self_test() -> int:
    """검사기 자기검증 — **검출과 위양성 양방향**으로 본다 (D-213).

    통과하는 것만 확인하면 「위반을 못 찾은 것」과 「그 자리를 안 본 것」을 구별할 수 없다.
    """
    real = {rel: _read_file(rel) for rel in CONSUMERS}
    cases: list[tuple[str, dict[str, str], bool]] = []

    # 1. 지금 저장소 — 위반 0
    cases.append(("현재 저장소", {}, False))

    # 2. 소비자가 import 를 잃으면 잡는다
    victim = "app/search/scoping.py"
    cases.append(
        ("소비자가 import 를 잃음", {victim: real[victim].replace("app.authz.visibility", "app.core.ownership")}, True),
    )

    # 3. import 는 **있는데** 입구를 안 부르면 잡는다 (규칙 1 의 둘째 갈래)
    no_call = (
        "from app.authz.visibility import RESOURCE_SEARCH\n\n"
        "def sql_clause(ctx):\n    return RESOURCE_SEARCH\n"
    )
    cases.append(("import 만 하고 안 부름", {victim: no_call}, True))

    # 4. 산문에만 적혀 있으면 **통과하면 안 된다** — import 도 호출도 docstring 안에만 있다.
    #    `check_scope_gates.py` 가 실제로 이 방식으로 한 번 뚫렸다.
    prose = (
        '"""from app.authz.visibility import effective_visibility_clause 를 쓴다고 적기만 한다."""\n'
        "def sql_clause(ctx):\n    return None\n"
    )
    cases.append(("산문에만 적혀 있음", {victim: prose}, True))

    # 5. 은퇴한 판정 부품을 되살리면 잡는다 (규칙 2)
    revived = real[victim] + "\n\ndef stored_ownership_clause(scope):\n    return None\n"
    cases.append(("은퇴한 부품 부활", {victim: revived}, True))

    failures = 0
    for name, overrides, expect_problem in cases:
        def read(rel: str, _o=overrides) -> str:
            return _o[rel] if rel in _o else _read_file(rel)

        problems, _, _ = check(read)
        got = bool(problems)
        if got != expect_problem:
            failures += 1
            print(f"[FAIL] self-test 「{name}」: 위반 {got} 인데 {expect_problem} 이어야 한다")
            for p in problems:
                print(f"       {p}")
    if failures:
        return 1
    print(f"[OK ] VISIBILITY_SELFTEST_OK (사례 {len(cases)}개, 검출·위양성 양방향)")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()

    rc = self_test()
    if rc:
        return rc
    problems, consumers, scanned = check(_read_file)
    if problems:
        print("VISIBILITY_SINGLE_SOURCE_FAILED")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(
        f"VISIBILITY_SINGLE_SOURCE_OK (소비자 {consumers}개가 {SOURCE} 를 지난다 · "
        f"은퇴한 판정 부품 {len(RETIRED)}개를 app 전체 {scanned}개 파일에서 확인)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
