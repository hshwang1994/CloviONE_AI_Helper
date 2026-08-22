"""마이그레이션에 얼려 둔 Knowledge Domain 값이 **코드의 표와 같은가** (S7 · 0003 과 같은 관용).

마이그레이션은 앱 코드를 import 하지 않는다 — 그 시점 스키마의 얼어붙은 스냅숏이어야
하기 때문이다. 그래서 어휘가 두 곳에 적히고, **두 곳에 적힌 값이 어긋나면 조용히 깨진다**:

  * 코드에 문서 출처를 하나 늘리고 마이그레이션의 CHECK 를 안 고치면 → 새 값이 DB 에서
    거절된다. 오류 메시지는 제약 이름뿐이라 아무도 원인을 못 찾는다.
  * 폴더 깊이 상한을 코드에서만 늘리면 → 앱은 통과시키고 트리거가 거절한다. 사용자에게는
    「폴더가 안 만들어진다」로만 보인다.
  * `path` 구분자가 갈리면 → 「이 폴더 아래 전부」가 한 건도 안 나온다. 이쪽은 오류조차
    안 난다.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from sqlalchemy import inspect, text

from app.knowledge import folders
from app.knowledge.models import (
    DREL_KINDS,
    MAX_FOLDER_DEPTH,
    MENTION_KINDS,
    SOURCE_TYPES,
    SPACE_OWNER_KINDS,
    VERSION_SOURCES,
)

pytestmark = pytest.mark.unit

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[2]
    / "alembic" / "versions" / "0004_knowledge_domain.py"
)


def _frozen(name: str) -> tuple[str, ...]:
    """마이그레이션이 얼려 둔 상수 튜플을 **글자로** 읽는다.

    import 하면 안 된다 — import 가 되는 순간 두 곳이 한 곳이 되고, 이 시험이 아무것도
    확인하지 않게 된다(그래도 초록이라 아무도 눈치채지 못한다).
    """
    source = MIGRATION.read_text(encoding="utf-8")
    match = re.search(rf"^{name}\s*=\s*\(([^)]*)\)", source, re.M)
    assert match, f"마이그레이션에서 {name} 을 못 찾았다"
    return tuple(re.findall(r'"([^"]+)"', match.group(1)))


def test_the_frozen_reader_is_not_vacuous():
    """이 파일의 다른 시험들이 **빈 튜플끼리 비교하며** 통과하지 않는지 먼저 본다."""
    assert len(_frozen("_SOURCE_TYPES")) >= 3


@pytest.mark.parametrize("frozen_name,code_values", [
    ("_SPACE_OWNER_KINDS", SPACE_OWNER_KINDS),
    ("_SOURCE_TYPES", SOURCE_TYPES),
    ("_VERSION_SOURCES", VERSION_SOURCES),
    ("_DREL_KINDS", DREL_KINDS),
    ("_MENTION_KINDS", MENTION_KINDS),
])
def test_every_frozen_vocabulary_matches_the_code(frozen_name, code_values):
    assert _frozen(frozen_name) == tuple(code_values), (
        f"{frozen_name} 이 코드와 다르다 — 새 값이 DB 에서 조용히 거절된다"
    )


def test_the_depth_limit_matches_the_code():
    source = MIGRATION.read_text(encoding="utf-8")
    match = re.search(r"^_MAX_FOLDER_DEPTH\s*=\s*(\d+)", source, re.M)
    assert match, "마이그레이션에서 _MAX_FOLDER_DEPTH 를 못 찾았다"
    assert int(match.group(1)) == MAX_FOLDER_DEPTH, (
        "앱은 통과시키고 트리거가 거절한다 — 사용자에게는 「폴더가 안 만들어진다」로만 보인다"
    )


def test_the_path_separator_matches_the_code():
    source = MIGRATION.read_text(encoding="utf-8")
    match = re.search(r'^_PATH_SEP\s*=\s*"([^"]*)"', source, re.M)
    assert match, "마이그레이션에서 _PATH_SEP 를 못 찾았다"
    assert match.group(1) == folders.PATH_SEP, (
        "구분자가 갈리면 「이 폴더 아래 전부」가 한 건도 안 나온다 — 오류조차 안 난다"
    )


# ── 스키마가 실제로 그렇게 섰는가 ───────────────────────────────────────────


def test_the_folder_triggers_exist(db):
    """둘 다 있어야 한다. BEFORE 만 있으면 옮긴 폴더의 **자손**이 옛 조상을 계속 가리킨다."""
    rows = {
        r[0] for r in db.execute(text(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
            "AND tgrelid = 'folders'::regclass"
        ))
    }
    assert rows == {"trg_folders_set_path", "trg_folders_move_subtree"}, rows


def test_the_body_column_is_real_jsonb_not_text(db):
    """`JsonText`(문자열 계약)가 아니라 진짜 `jsonb` 여야 한다 — 이 값은 블록 단위로 읽는다."""
    columns = {
        c["name"]: c for c in inspect(db.get_bind()).get_columns("document_versions")
    }
    assert str(columns["body"]["type"]) == "JSONB", columns["body"]["type"]


def test_every_knowledge_table_stands(db):
    names = set(inspect(db.get_bind()).get_table_names())
    expected = {
        "knowledge_spaces", "folders", "documents", "document_versions",
        "document_relations", "tags", "document_tags", "document_mentions",
    }
    assert expected <= names, sorted(expected - names)
