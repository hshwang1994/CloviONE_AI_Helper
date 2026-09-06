"""검색 재색인은 **한 행 때문에 통째로 죽지 않는다** (app/search/indexer.py).

## 무엇이 문제였나

사용자 색인 행의 `route` 는 `"/users?q=" + percent-encoding(표시 이름)` 이었다. 표시 이름
상한은 120자이고 한글 한 글자는 인코딩에서 아홉 자가 되므로 그 경로는 최대 1089자가 되는데,
`search_documents.route` 는 `String(300)` 이다. 한글 34자만 넘겨도 상한을 넘고, 넘치면 그
한 행이 아니라 **INSERT 배치 전체**가 `StringDataRightTruncation` 으로 죽었다. 이어서 세션이
못 쓰는 상태로 남아 뒤따르는 상태 기록까지 함께 터졌고, 화면에는 500 만 남았다.

재색인은 검색이 이상할 때 관리자가 누르는 복구 버튼이다. 이름을 길게 쓴 계정 하나가 그
복구 수단을 그 계정이 남아 있는 한 영원히 막았다.

## 무엇을 고정하는가

  * 상한 길이의 한글 이름을 가진 계정이 있어도 재색인은 성공하고, 그 사람도 색인에 든다.
  * 짧은 이름은 **그대로** 색인된다(반례) — 위 시험이 「길면 버린다」로 통과하지 못하게 한다.
"""

from __future__ import annotations

from urllib.parse import quote, unquote

import pytest
from sqlalchemy import select

from app.search.indexer import ROUTE_CHARS
from app.search.models import KIND_USER, SearchDocument

# 사이 파일(test_search_reindex_trigger.py)과 같은 이유로 전용 DB 를 쓴다(D-190).
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

MAX_HANGUL_NAME = "가" * 120


def _reindex(client, csrf: str):
    return client.post("/api/search/reindex", headers={"X-CSRF-Token": csrf})


def _user_row(db, user_id: str) -> SearchDocument | None:
    return db.execute(
        select(SearchDocument).where(
            SearchDocument.kind == KIND_USER, SearchDocument.ref_id == user_id
        )
    ).scalar_one_or_none()


def test_reindex_survives_a_max_length_hangul_display_name(client, login_as, db, make_user):
    long_named = make_user(
        "search-longname@goodmit.co.kr", display_name=MAX_HANGUL_NAME,
    )
    csrf = login_as("operator", email="reindex-longname-op@goodmit.co.kr")

    response = _reindex(client, csrf)
    assert response.status_code == 200, response.text
    body = response.json()["reindex"]
    assert body["status"] == "ok", body
    assert body["error"] is None

    db.expire_all()
    row = _user_row(db, long_named.id)
    assert row is not None, "긴 이름을 가진 사람이 색인에서 통째로 빠졌다"
    assert len(row.route) <= ROUTE_CHARS
    assert row.route.startswith("/users?q=")
    # 잘렸어도 **읽을 수 있는 경로**여야 한다 — percent escape 를 반쪽으로 자르면
    # 링크 자체가 깨진다. 디코딩해서 그 이름의 앞부분이 나오는지로 확인한다.
    decoded = unquote(row.route[len("/users?q="):])
    assert decoded, "검색어가 통째로 잘려 나갔다"
    assert MAX_HANGUL_NAME.startswith(decoded)


def test_a_short_display_name_is_indexed_whole(client, login_as, db, make_user):
    """반례 — 폭 안에 드는 이름은 한 글자도 안 잘린다."""
    short_named = make_user("search-shortname@goodmit.co.kr", display_name="김검색")
    csrf = login_as("operator", email="reindex-shortname-op@goodmit.co.kr")

    assert _reindex(client, csrf).status_code == 200

    db.expire_all()
    row = _user_row(db, short_named.id)
    assert row is not None
    assert row.route == "/users?q=" + quote("김검색")


# ── 「마지막 문」은 폭 있는 칸 전부여야 한다 ──────────────────────────────────
#
# 위 사고를 고친 문(`_fit_column`)은 스스로를 「색인 쓰기가 지나는 마지막 문」이라고 적어
# 두고서 route·url·subtitle·sort_key 네 칸만 봤다. `kind`·`ref_id`·`owner_kind`·
# `owner_dept_id`·`owner_project_id` 다섯은 그냥 지나갔다 — 지금 그 칸에 들어가는 값이
# id 뿐이라 사고가 안 났을 뿐이고, 그 말을 믿고 새 값을 만든 사람이 다섯 중 하나를 고르면
# 위와 똑같이 재구축 전체가 죽는다. 문의 목록은 손으로 적지 않고 매퍼에서 뽑는다.


def test_the_gate_covers_every_bounded_column_of_the_index_table():
    from sqlalchemy import String

    from app.search.indexer import _COLUMN_LIMITS

    bounded = {
        column.name: column.type.length
        for column in SearchDocument.__table__.columns
        if isinstance(column.type, String) and column.type.length
    }
    assert bounded, "전제가 깨졌다 — 폭이 정해진 칸이 하나도 없다"
    assert _COLUMN_LIMITS == bounded, (
        "문이 보는 칸과 표가 가진 칸이 다르다 — 빠진 칸 하나가 배치 전체를 죽인다: "
        f"{set(bounded) - set(_COLUMN_LIMITS)}"
    )


def test_an_overlong_ownership_value_is_cut_instead_of_killing_the_batch():
    """소유 축 세 칸도 폭이 있다 — 넘치면 그 행이 아니라 INSERT 배치 전체가 죽는다."""
    from app.search.indexer import _COLUMN_LIMITS, _fit_column

    for field in ("kind", "ref_id", "owner_kind", "owner_dept_id", "owner_project_id"):
        fitted = _fit_column(field, "x" * 500)
        assert len(fitted) <= _COLUMN_LIMITS[field], f"{field} 가 문을 그냥 지나갔다"


def test_a_value_that_fits_is_never_touched():
    """반례 — 폭 안에 드는 값은 한 글자도 안 바뀐다(위 시험이 「전부 자른다」로 통과하지 못하게)."""
    from app.search.indexer import _fit_column

    assert _fit_column("owner_kind", "department") == "department"
    assert _fit_column("ref_id", "ot-doc-a1") == "ot-doc-a1"
    assert _fit_column("title", "폭이 없는 칸은 그대로다") == "폭이 없는 칸은 그대로다"
