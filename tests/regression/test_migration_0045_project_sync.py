"""프로젝트 동기화 컬럼과 **앞 회차를 깨지 않았다**는 보증 (옛 0045).

qa-contract-change: 옛 파일은 SQLite alembic 체인의 upgrade→downgrade→upgrade 왕복을 돌려 이 성질을 확인했다. 그 체인은 은퇴했으므로(D-189) 그 형태의 시험은 성립하지 않는다 — 못박는 성질은 그대로 두고, 체인이 만들어 내던 것을 0001_pg_baseline 이 빠짐없이 갖고 있는가로 대상만 옮겼다.

옛 파일이 왕복을 본 이유는 `drop_column` 이 SQLite 에서 **테이블 재생성**이라, 되돌리는 순간
그 표의 행과 인덱스가 통째로 새로 만들어졌기 때문이다. 되돌릴 체인이 없어진 지금 그 자리를
대신하는 것은 «한 파일이 빠짐없이 담았는가» 다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

pytestmark = pytest.mark.regression

NEW_PROJECT_COLUMNS = {
    "notion_progress_pct",
    "notion_status",
    "notion_owner_ids",
    "notion_missing_at",
    "notion_last_edited",
    "notion_synced_at",
    "notion_sync_error",
}

# 앞 회차(0044)가 만든 것 중 **함께 날아가면 안 되는** 것들.
COLUMNS_0044_MUST_SURVIVE = {
    "progress_pct", "health_score", "archived_at", "notion_page_id", "dept_id", "code",
}


def _cols(db, table: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(table)}


def test_the_sync_columns_are_all_there(db):
    missing = NEW_PROJECT_COLUMNS - _cols(db, "projects")
    assert not missing, f"기준선이 안 만든 컬럼이 있다: {missing}"


def test_the_earlier_columns_survived(db):
    """새 컬럼을 더하면서 앞 회차의 컬럼을 밀어내지 않았는가."""
    missing = COLUMNS_0044_MUST_SURVIVE - _cols(db, "projects")
    assert not missing, f"앞 회차 컬럼이 사라졌다: {missing}"


def test_the_sync_singleton_table_exists(db):
    assert "project_sync_state" in set(inspect(db.get_bind()).get_table_names())
    assert {"id", "status", "updated_at"} <= _cols(db, "project_sync_state")


def test_the_project_code_is_unique_in_one_org(db):
    """같은 코드의 프로젝트가 둘이 되면 티켓이 어느 쪽에 붙을지 아무도 모른다 — 그리고 그
    상태는 화면상 정상으로 보인다.

    막는 것은 이제 `uq_projects_code` 다(D-282). 옛 `uq_projects_org_code` 는 0012 가 지웠고,
    그래서 코드 문자열도 옛 자유 형식(`DUP`)이 아니라 `ck_projects_code_shape` 가 재는 여섯
    글자여야 한다 — 짧은 값을 쓰면 유니크가 아니라 모양에서 먼저 걸려, 이 시험은 자기가
    보려던 것을 못 본 채 초록이 된다.
    """
    from sqlalchemy.exc import IntegrityError

    from app.org.constants import DEFAULT_ORG_ID
    from app.projects.models import Project

    db.add(Project(name="A", code="ABCDEF", org_id=DEFAULT_ORG_ID))
    db.flush()
    db.add(Project(name="B", code="ABCDEF", org_id=DEFAULT_ORG_ID))
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    # 어느 제약이 막았는지 확인한다. 다른 이유(NOT NULL·FK)로 난 IntegrityError 도 위
    # `raises` 는 그대로 통과시키므로, 이름을 안 보면 코드 유니크가 사라진 날에도 초록이다.
    assert "uq_projects_code" in str(caught.value), (
        f"코드 유니크가 아닌 다른 제약이 막았다: {caught.value}"
    )
    db.rollback()


def test_the_same_code_in_a_different_org_is_refused_too(db, two_orgs):
    """유니크는 이제 **전역**이다 — 조직이 다르다는 이유로 같은 코드를 내주지 않는다.

    옛 계약은 정반대였다: 유니크가 (org_id, code) 라 두 회사가 같은 코드를 쓸 수 있었다.
    그 자유를 접은 이유는 티켓 이름이다. 티켓은 `<CODE>-<SEQ>` 로 불리고 그 문자열은 링크와
    문서와 대화로 조직 밖까지 흘러 다니는데, 거기에는 어느 조직인지가 안 붙어 있다. 두
    조직이 `ABCDEF` 를 나눠 쓰면 `ABCDEF-37` 이 서로 다른 두 티켓의 이름이 되고, 그 이름을
    받은 사람은 어느 쪽을 열어야 하는지 답할 수 없다.
    """
    from sqlalchemy.exc import IntegrityError

    from app.projects.models import Project

    db.add(Project(name="A", code="BCDEFG", org_id=two_orgs.org_a_id))
    db.flush()
    db.add(Project(name="B", code="BCDEFG", org_id=two_orgs.org_b_id))
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    assert "uq_projects_code" in str(caught.value), (
        f"조직이 아니라 다른 제약이 막았다 — 전역 유니크를 확인한 것이 아니다: {caught.value}"
    )
    db.rollback()
