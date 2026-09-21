"""검색 접기 규칙 — 파이썬 · SQL · 말뭉치가 **한 글자도 안 다르게** 같은 값을 내는가 (D-495).

## 무엇을 못박는가

질의는 파이썬이 접고(`app/core/search_text.py::fold`) 대상은 DB 가 접는다(`search_fold()`,
alembic 0030). 두 구현이 한 글자라도 다르게 접으면 그 글자가 든 행은 **영원히 안 걸린다** —
오류도 없고 로그도 없어서 사용자는 「검색이 가끔 안 된다」고만 느낀다. 그래서 세 번째 증인을
둔다: 공용 말뭉치 `tests/fixtures/search_fold_corpus.json`. 프런트 구현도 같은 파일을 읽는다.

`sql: false` 인 사례는 PG 의 text 가 담지 못하는 글자(NUL)를 든 것이라 파이썬만 잰다.

## 함께 보는 것

  * 마이그레이션이 얼려 둔 삭제 목록이 파이썬의 `STRIP_CODEPOINTS` 와 같은가 — 말뭉치에 없는
    코드포인트가 한쪽에만 들어가도 이 시험이 잡는다.
  * `escape_like` · `pattern_for` 의 경계 — 빈 바늘이 `LIKE '%%'` 가 되지 않는가.
  * `SearchDocument` 의 접힌 열이 ORM 에서 어떻게 움직이는가 — DB 가 계산하고, 앱은 쓰지
    않고, 목록 조회는 읽지 않고, 원문을 고치면 따라 바뀐다.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect, literal, select, text

from app.core.search_text import (
    FOLD_VERSION,
    MAX_QUERY_CHARS,
    STRIP_CODEPOINTS,
    contains_folded,
    escape_like,
    fold,
    like_folded,
    like_pattern,
    matches_folded,
    normalize_query,
    pattern_for,
)
from app.search.models import SearchDocument

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
CORPUS = json.loads((ROOT / "tests" / "fixtures" / "search_fold_corpus.json").read_text("utf-8"))
MIGRATION = ROOT / "alembic" / "versions" / "0030_search_fold.py"

FOLD_CASES = CORPUS["fold"]
DISPLAY_CASES = CORPUS["display"]
SQL_CASES = [case for case in FOLD_CASES if case["sql"]]

NOW = datetime(2026, 9, 21, 9, 0, 0)


def test_the_corpus_is_not_vacuous():
    """아래 시험들이 **빈 표끼리 비교하며** 통과하지 않는지 먼저 본다."""
    assert len(FOLD_CASES) >= 60, f"접기 사례가 {len(FOLD_CASES)}건뿐이다"
    assert len(DISPLAY_CASES) >= 8, f"표시형 사례가 {len(DISPLAY_CASES)}건뿐이다"
    assert len(SQL_CASES) >= 55, f"SQL 로 잴 사례가 {len(SQL_CASES)}건뿐이다"
    names = [case["name"] for case in FOLD_CASES]
    assert len(names) == len(set(names)), "사례 이름이 겹친다 — 실패를 짚을 수 없다"
    # 말뭉치가 「아무것도 안 바꾸는 사례」만으로 채워지면 규칙을 통째로 빼도 통과한다.
    changed = [case for case in FOLD_CASES if case["fold"] != case["input"]]
    assert len(changed) >= 50, f"입력과 결과가 다른 사례가 {len(changed)}건뿐이다"


# ── 파이썬 = 말뭉치 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", FOLD_CASES, ids=[case["name"] for case in FOLD_CASES])
def test_python_fold_matches_the_corpus(case):
    assert fold(case["input"]) == case["fold"]


@pytest.mark.parametrize("case", DISPLAY_CASES, ids=[case["name"] for case in DISPLAY_CASES])
def test_the_display_form_matches_the_corpus(case):
    assert normalize_query(case["input"]) == case["display"]


def test_fold_is_idempotent_over_the_corpus():
    """접은 값을 다시 접어도 같다 — 저장된 사본을 한 번 더 접는 경로가 생겨도 어긋나지 않는다."""
    drifted = [case["name"] for case in FOLD_CASES if fold(case["fold"]) != case["fold"]]
    assert drifted == []


# ── SQL = 말뭉치 ──────────────────────────────────────────────────────────────


def test_sql_fold_matches_the_corpus(db):
    """🔴 대상 쪽 짝. 마이그레이션이 만든 `search_fold()` 가 말뭉치와 같은 값을 내는가."""
    mismatched = {}
    checked = 0
    for case in SQL_CASES:
        got = db.execute(text("SELECT search_fold(:s)"), {"s": case["input"]}).scalar()
        checked += 1
        if got != case["fold"]:
            mismatched[case["name"]] = (got, case["fold"])
    assert checked == len(SQL_CASES) and checked >= 55
    assert mismatched == {}, f"SQL 이 말뭉치와 다르게 접는다: {mismatched}"


def test_sql_fold_passes_null_through(db):
    """NULL 은 NULL 이다. 빈 문자열로 바꾸면 `IS NULL` 로 거르던 호출부가 조용히 달라진다."""
    assert db.execute(text("SELECT search_fold(NULL)")).scalar() is None


def test_the_sql_function_is_immutable_and_versioned(db):
    """생성 열은 IMMUTABLE 함수만 받는다. 주석의 판이 코드의 판과 같아야 한다."""
    volatility, comment = db.execute(text(
        "SELECT p.provolatile, obj_description(p.oid, 'pg_proc') FROM pg_proc p "
        "WHERE p.proname = 'search_fold'"
    )).one()
    assert volatility == "i"
    assert f"search_fold v{FOLD_VERSION} " in (comment or ""), comment


def _frozen_strip_class() -> set[int]:
    """마이그레이션이 얼려 둔 정규식 문자 집합을 **글자로** 읽어 코드포인트로 편다.

    import 하지 않는다 — import 하면 두 곳이 한 곳이 되고, 이 시험이 아무것도 확인하지 않는다.
    """
    source = MIGRATION.read_text(encoding="utf-8")
    match = re.search(r"'\[((?:\\u[0-9A-Fa-f]{4}|-)+)\]\+'", source)
    assert match, "마이그레이션에서 삭제 문자 집합을 못 찾았다"
    body = match.group(1)
    points: set[int] = set()
    for item in re.finditer(r"\\u([0-9A-Fa-f]{4})(?:-\\u([0-9A-Fa-f]{4}))?", body):
        start = int(item.group(1), 16)
        end = int(item.group(2), 16) if item.group(2) else start
        points.update(range(start, end + 1))
    return points


def test_the_frozen_sql_strip_set_is_the_python_strip_set():
    """말뭉치에 없는 코드포인트가 한쪽 목록에만 들어가도 여기서 잡힌다. NUL 만 파이썬 전용이다."""
    frozen = _frozen_strip_class()
    assert len(frozen) >= 20, f"얼린 목록이 {len(frozen)}개뿐이다 — 읽기가 헛돈다"
    assert frozen == set(STRIP_CODEPOINTS) - {0x0000}


# ── escape 와 빈 바늘 ─────────────────────────────────────────────────────────


def test_escape_like_escapes_the_escape_character_first():
    backslash = chr(92)
    assert escape_like("100%") == "100" + backslash + "%"
    assert escape_like("a_b") == "a" + backslash + "_b"
    # `\` 를 나중에 바꾸면 `%` 앞에 붙인 escape 가 두 번 바뀌어 `\\%` 가 된다 — `%` 가 다시 와일드카드다.
    assert escape_like(backslash + "%") == backslash * 2 + backslash + "%"
    assert escape_like("평범한 글") == "평범한 글"


def test_like_pattern_wraps_an_escaped_needle():
    assert like_pattern("현황제외") == "%현황제외%"
    assert like_pattern("%") == "%" + chr(92) + "%%"


@pytest.mark.parametrize("raw", [None, "", "   ", "\u200b", "\u3000\u3000", "\ufeff\u00ad"])
def test_an_empty_needle_is_no_pattern_at_all(raw):
    """🔴 접은 뒤 비면 `None` 이다. 빈 바늘은 `LIKE '%%'` 가 되어 전 행에 걸린다."""
    assert pattern_for(raw) is None
    assert contains_folded([SearchDocument.title], raw) is None
    assert matches_folded("아무 제목", raw) is True


def test_pattern_for_folds_the_display_form():
    assert pattern_for("  현황   제외 ") == "%현황제외%"
    assert pattern_for("ClovirONE") == "%clovirone%"
    assert pattern_for("\uff23\uff4c\uff4f\uff56\uff49\uff52") == "%clovir%"


def test_pattern_for_caps_the_query_before_folding():
    long_query = "가" * (MAX_QUERY_CHARS + 50)
    assert pattern_for(long_query) == "%" + "가" * MAX_QUERY_CHARS + "%"


def test_contains_folded_needs_a_column():
    with pytest.raises(ValueError):
        contains_folded([], "현황")


def test_matches_folded_is_the_python_twin():
    assert matches_folded("현황 제외 목록", "현황제외")
    assert matches_folded("현황제외 목록", "  현황   제외 ")
    assert matches_folded("ClovirONE 배포", "clovirone")
    assert matches_folded("\uff23\uff4c\uff4f\uff56\uff49\uff52\uff2f\uff2e\uff25", "CLOVIRONE")
    assert not matches_folded("현황 보고", "현황제외")
    assert not matches_folded(None, "현황")
    # 글자 그대로의 `%` 는 `%` 만 찾는다.
    assert matches_folded("달성률 100%", "%")
    assert not matches_folded("달성률 백 퍼센트", "%")


def test_the_escape_character_means_the_same_thing_in_postgres(db):
    """escape 문자가 PG 쪽에서도 같은 뜻인가. `_` 가 아무 글자 하나로 새면 `abc` 가 걸린다."""
    def hit(value: str, raw: str) -> bool:
        return bool(db.execute(select(like_folded(literal(value), pattern_for(raw)))).scalar())

    assert hit("a_c", "a_c") and not hit("abc", "a_c")
    assert hit("100%", "0%") and not hit("1000", "0%")
    assert hit("C:\\temp", "c:\\") and not hit("C:/temp", "c:\\")


# ── ORM 이 접힌 열을 다루는 방식 ──────────────────────────────────────────────


def _document(db, title: str, body: str = "") -> SearchDocument:
    row = SearchDocument(
        kind="ticket", ref_id=f"fold-{title}", title=title, body=body,
        owner_user_ids="", route="/x", indexed_at=NOW,
    )
    db.add(row)
    db.flush()
    return row


def _stored(db, row_id: str) -> tuple[str, str]:
    return tuple(db.execute(
        select(SearchDocument.title_fold, SearchDocument.body_fold)
        .where(SearchDocument.id == row_id)
    ).one())


def test_the_database_computes_the_folded_copy_on_insert(db):
    row = _document(db, "현황 제외", "\uff23\uff4c\uff4f\uff56\uff49\uff52\uff2f\uff2e\uff25 배포")
    assert _stored(db, row.id) == ("현황제외", "clovirone배포")


def test_editing_the_source_refreshes_the_folded_copy(db):
    """원문을 고치면 접힌 값이 **같은 행 안에서** 따라 바뀐다. ORM 이 옛 값을 붙들지 않는다."""
    row = _document(db, "옛 제목")
    assert row.title_fold == "옛제목"
    row.title = "새 제목"
    db.flush()
    assert row.title_fold == "새제목", "ORM 이 고치기 전 접힌 값을 그대로 들고 있다"
    assert _stored(db, row.id)[0] == "새제목"


def test_the_application_never_writes_the_folded_copy(db):
    """생성 열에 값을 넣으면 PG 가 거절한다 — 인덱서의 쓰기 목록에 그 이름이 없어야 한다."""
    from sqlalchemy import update
    from sqlalchemy.exc import DBAPIError

    from app.search import indexer

    assert not {"title_fold", "body_fold"} & set(indexer._FIELDS)
    columns = inspect(SearchDocument).columns
    assert columns["title_fold"].computed is not None
    assert columns["body_fold"].computed is not None

    # 반례 — DB 가 정말로 막는가. 막지 않으면 위 목록이 유일한 방어선이 된다.
    row = _document(db, "쓰기 확인")
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(
                update(SearchDocument).where(SearchDocument.id == row.id).values(title_fold="x")
            )
    assert _stored(db, row.id)[0] == "쓰기확인"


def test_listing_rows_does_not_fetch_the_folded_copy():
    """목록 · 재색인은 행을 통째로 읽는다. 대조용 사본까지 끌어오면 본문을 두 번 보내는 셈이다."""
    sql = str(select(SearchDocument).compile())
    assert "search_documents.title" in sql and "search_documents.body" in sql
    assert "title_fold" not in sql and "body_fold" not in sql


def test_inserting_does_not_fetch_the_folded_copy_back(db):
    """INSERT 가 접힌 사본을 `RETURNING` 으로 되받지 않는다. 읽는 사람이 있을 때만 읽어 온다.

    SQLAlchemy 기본값은 생성 열을 INSERT 마다 돌려받는다 — 재색인이 행 수천 건을 넣는 자리라
    그 값이 곧 쓸 데 없는 전송량이다(`SearchDocument.__mapper_args__`).
    """
    from sqlalchemy import event

    engine = db.get_bind().engine
    inserts: list[str] = []

    def capture(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO SEARCH_DOCUMENTS"):
            inserts.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        row = _document(db, "되받기 확인", "본문 사본")
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert len(inserts) == 1, f"INSERT 를 {len(inserts)}번 봤다 — 관찰이 헛돈다"
    assert "title_fold" not in inserts[0] and "body_fold" not in inserts[0], inserts[0]
    # 되받지 않았어도 값은 맞다 — 읽을 때 한 번 읽어 온다.
    assert (row.title_fold, row.body_fold) == ("되받기확인", "본문사본")
