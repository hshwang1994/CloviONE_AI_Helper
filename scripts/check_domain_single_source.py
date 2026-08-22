"""도메인의 **쓰기 입구가 하나인지** 확인한다 (S6 Exit · S7 Exit · D-195 · D-196 · D-198).

## 왜 이 검사가 생겼는가

S5 가 배운 것을 그대로 적용한다: **「같은 규칙을 따른다」는 주석은 증거가 아니다.**
아래 성질들은 전부 「한 곳에서만 쓴다」에 기대고 있고, 하나도 어겨도 오류가 안 난다.

### Work Domain (S6)

| 성질 | 어기면 |
|---|---|
| `canonical_key` 는 **트리거만** 쓴다 (D-195) | 앱이 쓴 값과 트리거가 만들 값이 갈리고, 그 티켓은 검색으로도 링크로도 못 찾는다 |
| 번호는 **`app/work/numbering.py`** 만 발급한다 (D-196) | 「읽고 +1」이 한 군데만 생겨도 중복 번호가 나오고, 유니크가 잡을 때는 사용자가 저장을 누른 뒤다 |
| Key 는 **`app/work/keys.py`** 만 잡는다 (D-196) | 대장이 모르는 Key 가 생기고, 옛 canonical 이 별칭으로 안 남아 옛 링크가 전부 죽는다 |
| 상하위는 **`app/work/relations.py`** 만 쓴다 | 계층이 두 벌이 되고, 갈라진 뒤에는 갈라진 쪽을 아무도 못 고친다 |

### Knowledge Domain (S7)

S6 이 넘긴 그대로다 — **새 자원의 쓰기 입구를 하나로 둔다.** Block JSON 정본(D-198)이
정확히 같은 성질을 요구한다: 정본이 하나여야 파생이 갈라지지 않는다.

| 성질 | 어기면 |
|---|---|
| 파생(`body_markdown`·`body_text`)은 **`app/knowledge/blocks.py`** 만 만든다 (D-198) | 같은 판이 화면과 검색에서 다른 글이 된다. 어긋남은 「검색해도 안 나오는 문서」로만 드러나고 아무도 신고하지 않는다 |
| 판은 **`app/knowledge/versions.py`** 만 쌓는다 | 한쪽이 `version_no` 를 다르게 매기거나 파생을 안 만들고, 그 문서는 이력이 끊긴 채로 남는다 — 끊긴 이력은 복구할 수 없다 |
| 폴더의 `path`·`depth` 는 **트리거만** 쓴다 (D-244) | `parent_id` 와 `path` 가 갈리고, 「이 폴더 아래 전부」가 조용히 틀린 답을 낸다 |
| 멘션 표는 **`app/knowledge/mentions.py`** 만 쓴다 | 「나를 언급한 문서」에 3년 전 지워진 문장이 계속 나온다 |

## 한계 (일부러 적어 둔다)

정적 검사다. **증명이 아니라 「생각조차 안 한 곳」을 잡는 그물**이다. 이름을 바꿔
같은 일을 하는 코드는 못 잡는다 — 그쪽은
`tests/integration/test_ticket_numbering_race.py` ·
`tests/regression/test_ticket_key_resolution.py` ·
`tests/integration/test_knowledge_folder_tree.py` 가 실제 행으로 본다.
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

# (무엇을 쓰는가, 그 값을 쓸 수 있는 파일들, 찾는 정규식, 어기면 무슨 일이 나는가)
RULES: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    (
        "canonical_key",
        (),   # **아무 파일도** 못 쓴다. DB 트리거가 유일한 작성자다 (D-195).
        r"\.canonical_key\s*=(?!=)|canonical_key\s*=\s*[^=]",
        "앱이 쓴 값과 트리거가 파생시킬 값이 갈린다 — 그 티켓은 검색으로도 링크로도 안 잡힌다",
    ),
    (
        "project_ticket_counters",
        ("app/work/numbering.py",),
        r"project_ticket_counters",
        "채번이 두 곳이 되면 같은 번호가 두 번 나온다 (D-196)",
    ),
    (
        "project_key_registry",
        ("app/work/keys.py",),
        r"ProjectKeyRegistry\s*\(",
        "대장이 모르는 Key 가 생기고, Key 소유가 영구라는 근거가 무너진다 (D-196)",
    ),
    (
        "projects.code 대입",
        ("app/work/keys.py",),
        r"\.code\s*=\s*(?!=)(?!None)",
        "옛 canonical 이 별칭으로 안 남아 옛 링크가 전부 죽는다 (D-195)",
    ),
    (
        "subtask_of 관계",
        ("app/work/relations.py",),
        r"TicketRelation\s*\(",
        "계층이 두 벌이 되고, 갈라진 뒤에는 갈라진 쪽을 아무도 못 고친다",
    ),
    # ── Knowledge Domain (S7) ───────────────────────────────────────────────
    (
        "본문 파생(body_markdown · body_text)",
        (
            "app/knowledge/blocks.py",
            "app/knowledge/versions.py",
            # ⚠️ 아래 다섯은 **다른 표의 같은 이름 컬럼**이다.
            # `document_cache.body_markdown`·`tickets.body_markdown` 은 Notion 미러가
            # 들고 있는 본문이고, 정본이 저쪽에 있으므로 파생이라는 개념 자체가 없다.
            # 정적 검사는 이름만 보므로 여기서 이름으로 열어 준다 — S14 가 미러를
            # 걷어내면 이 다섯 줄도 함께 사라지고, 그때 규칙은 저절로 더 좁아진다.
            "app/team_docs/repository_notion.py",
            "app/team_docs/router.py",
            "app/team_docs/service.py",
            "app/tickets/repository_notion.py",
            "app/tickets/router.py",
            "app/tickets/service.py",
        ),
        r"body_markdown\s*=|body_text\s*=",
        "같은 판이 화면과 검색에서 다른 글이 된다 — 「검색해도 안 나오는 문서」로만 드러난다 (D-198)",
    ),
    (
        "판 생성",
        ("app/knowledge/versions.py",),
        r"DocumentVersion\s*\(",
        "이력이 끊긴 문서가 생기고, 끊긴 이력은 되돌릴 수도 다시 계산할 수도 없다",
    ),
    (
        "폴더 path · depth 대입",
        (),   # **아무 파일도** 못 쓴다. DB 트리거가 유일한 작성자다 (D-244).
        # 받는 쪽이 폴더일 때만 본다. `.path` 와 `.depth` 는 흔한 속성 이름이라
        # 그냥 걸면 관계없는 파일이 전부 위반이 되고, 그러면 사람이 검사를 끈다.
        r"\b\w*[Ff]older\w*\.(?:path|depth)\s*=(?!=)"
        r"|Folder\s*\([^)]*(?:path|depth)\s*=",
        "`parent_id` 와 `path` 가 갈리고, 「이 폴더 아래 전부」가 조용히 틀린 답을 낸다",
    ),
    (
        "멘션 표",
        ("app/knowledge/mentions.py",),
        r"DocumentMention\s*\(",
        "「나를 언급한 문서」에 3년 전 지워진 문장이 계속 나온다",
    ),
)

# 계층을 **읽는** 자리. 미러 컬럼을 직접 읽으면 관계 표와 갈라진다.
HIERARCHY_READERS_FORBIDDEN = r"\.parent_page_id\b"
HIERARCHY_ALLOWED = (
    "app/tickets/models.py",      # 컬럼 정의
    "app/tickets/sync.py",        # 미러에 받아 적는 자리 (파생의 입력)
    "app/work/relations.py",      # 그 입력을 관계로 옮기는 유일한 함수
    "app/reports/notion_source.py",  # 외부 응답 파서 — 아직 도메인이 아니다
    "app/notion_console/router.py",  # Notion 콘솔의 요청 필드(다른 뜻의 같은 이름)
    "app/notion_console/probe_notion.py",
)

DOCSTRING_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')
COMMENT_RE = re.compile(r"#[^\n]*")


def code_only(text: str) -> str:
    """주석과 docstring 을 뺀 실행 코드만.

    이 저장소는 「왜」를 길게 적는 것이 규칙이라 컬럼 이름이 산문에 자주 나온다. 그대로
    두면 **설명만 한 파일**이 전부 위반으로 잡혀 검사가 소음이 된다(그리고 소음이 되면
    사람이 끈다).
    """
    return COMMENT_RE.sub("", DOCSTRING_RE.sub("", text))


# 표를 **정의**하는 파일. 정의는 쓰기가 아니다 — 여기까지 잡으면 스키마를 적을 자리가
# 없어지고, 그러면 사람이 이 검사를 끈다.
SCHEMA_FILES = (
    "app/work/models.py",
    "app/tickets/models.py",
    "app/knowledge/models.py",
)


def _targets() -> list[str]:
    return sorted(
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "app").rglob("*.py")
        if p.relative_to(ROOT).as_posix() not in SCHEMA_FILES
    )


def check(read, files: list[str]) -> tuple[list[str], int]:
    """`read(rel) -> str` 와 훑을 파일 목록을 주면 (위반, 훑은 파일 수)."""
    problems: list[str] = []
    for rel in files:
        src = code_only(read(rel))
        for what, allowed, pattern, consequence in RULES:
            if rel in allowed:
                continue
            if re.search(pattern, src):
                where = ", ".join(allowed) if allowed else "어느 파일도 아니다(DB 트리거만)"
                problems.append(
                    f"{rel}: {what} 를 여기서 쓴다 — 쓸 수 있는 자리는 {where}. {consequence}"
                )
        if rel not in HIERARCHY_ALLOWED and re.search(HIERARCHY_READERS_FORBIDDEN, src):
            problems.append(
                f"{rel}: 계층을 `parent_page_id` 로 읽는다 — 정본은 `ticket_relations` 다"
                " (`app/work/relations.py::parent_map`)"
            )
    return problems, len(files)


def _read_file(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def self_test() -> int:
    """검사기 자기검증 — **검출과 위양성 양방향**으로 본다 (D-213).

    통과하는 것만 확인하면 「위반을 못 찾은 것」과 「그 자리를 안 본 것」을 구별할 수 없다.
    """
    victim = "app/tickets/service.py"
    # 파생 규칙은 위 `victim` 을 이름으로 열어 뒀다(옛 미러의 같은 이름 컬럼). 그래서
    # Knowledge 사례는 **다른 파일**로 낸다 — 안 그러면 검출 쪽 사례가 조용히 통과한다.
    other = "app/home/service.py"
    cases: list[tuple[str, dict[str, str], bool]] = [
        ("현재 저장소", {}, False),
        (
            "앱이 canonical_key 를 쓴다",
            {victim: "def f(t):\n    t.canonical_key = 'X-1'\n"},
            True,
        ),
        (
            "다른 곳에서 채번한다",
            {
                victim: "def f(db):\n"
                "    db.execute('UPDATE project_ticket_counters SET last_seq = 1')\n"
            },
            True,
        ),
        (
            "다른 곳에서 Key 를 잡는다",
            {victim: "def f(db):\n    db.add(ProjectKeyRegistry(key='X'))\n"},
            True,
        ),
        (
            "다른 곳에서 projects.code 를 갈아 끼운다",
            {victim: "def f(p):\n    p.code = 'NEW'\n"},
            True,
        ),
        (
            "다른 곳에서 상하위 관계를 만든다",
            {victim: "def f(db):\n    db.add(TicketRelation(kind='subtask_of'))\n"},
            True,
        ),
        (
            "다른 곳에서 계층을 미러 컬럼으로 읽는다",
            {victim: "def f(row):\n    return row.parent_page_id\n"},
            True,
        ),
        # ── Knowledge Domain (S7) ──────────────────────────────────────────
        (
            "다른 곳에서 본문 파생을 만든다",
            {other: "def f(v, md):\n    v.body_markdown = md\n"},
            True,
        ),
        (
            "다른 곳에서 판을 쌓는다",
            {other: "def f(db):\n    db.add(DocumentVersion(version_no=1))\n"},
            True,
        ),
        (
            "다른 곳에서 폴더 path 를 계산한다",
            {other: "def f(folder, parent):\n    folder.path = parent.path + folder.id\n"},
            True,
        ),
        (
            "다른 곳에서 폴더 depth 를 계산한다",
            {other: "def f(folder, parent):\n    folder.depth = parent.depth + 1\n"},
            True,
        ),
        (
            "다른 곳에서 멘션 행을 만든다",
            {other: "def f(db):\n    db.add(DocumentMention(block_id='b'))\n"},
            True,
        ),
        # 위양성 쪽 — 폴더가 아닌 것의 `.path`·`.depth` 는 통과해야 한다. 둘 다 흔한
        # 속성 이름이라, 여기서 걸리면 관계없는 파일이 전부 위반이 되고 검사가 꺼진다.
        (
            "폴더가 아닌 것의 path 와 depth",
            {
                other: "def f(lock, node):\n"
                "    lock.path = '/var/run/x'\n"
                "    node.depth = node.depth + 1\n"
            },
            False,
        ),
        # 위양성 쪽 — **산문에만** 나오면 통과해야 한다. 이 저장소는 컬럼 이름을 주석에
        # 자주 쓰므로, 여기서 걸리면 검사가 소음이 되어 사람이 꺼 버린다.
        (
            "산문에만 나온다",
            {
                victim: '"""canonical_key 는 트리거가 만든다. parent_page_id 는 입력이다."""\n'
                "# project_ticket_counters 는 app/work/numbering.py 가 쓴다\n"
                "def f():\n    return None\n"
            },
            False,
        ),
    ]

    failures = 0
    for name, overrides, expect_problem in cases:
        def read(rel: str, _o=overrides) -> str:
            return _o[rel] if rel in _o else _read_file(rel)

        problems, _ = check(read, list(overrides) if overrides else _targets())
        got = bool(problems)
        if got != expect_problem:
            failures += 1
            print(f"[FAIL] self-test 「{name}」: 위반 {got} 인데 {expect_problem} 이어야 한다")
            for p in problems:
                print(f"       {p}")
    if failures:
        return 1
    print(f"[OK ] DOMAIN_SINGLE_SOURCE_SELFTEST_OK (사례 {len(cases)}개, 검출·위양성 양방향)")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()

    rc = self_test()
    if rc:
        return rc
    files = _targets()
    problems, scanned = check(_read_file, files)
    if problems:
        print("DOMAIN_SINGLE_SOURCE_FAILED")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(
        f"DOMAIN_SINGLE_SOURCE_OK (규칙 {len(RULES) + 1}개를 app 전체 {scanned}개 "
        "파일에서 확인)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
