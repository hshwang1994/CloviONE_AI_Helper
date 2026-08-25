"""마이그레이션이 심은 Work Domain 값이 **코드의 표와 같은가** (S6 · 0002 와 같은 관용).

qa-contract-change: 예약 Key 네임스페이스는 옛 `GIT-*` 이름을 남이 먼저 가져가지 못하게 막으려고만 있었고, 새 코드 정책은 그 옛 이름을 아예 옮기지 않으며 코드도 서버가 짓는다(D-283). 그래서 「예약 Key 가 코드와 DB 에 같이 적혀 있는가」는 지킬 대상이 사라진 성질이고, 대장 표(`project_key_registry`)도 0012 가 지웠다. 상태 어휘를 못박는 단언은 한 줄도 줄이지 않았다.

마이그레이션은 앱 코드를 import 하지 않는다 — 그 시점 스키마의 얼어붙은 스냅숏이어야
하기 때문이다. 그래서 상태 어휘가 코드와 마이그레이션 두 곳에 적히고, **두 곳에 적힌
값이 어긋나면 조용히 깨진다**: 코드에 상태를 하나 늘리고 마이그레이션을 안 고치면 새
설치에서만 그 상태가 칸반 열로 안 나온다. 그 티켓들은 「분류되지 않음」에 모이고,
아무도 원인을 모른다.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from sqlalchemy import select

from app.work import workflow
from app.work.models import TicketStatus

pytestmark = pytest.mark.unit

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[2]
    / "alembic" / "versions" / "0003_work_domain.py"
)


def test_every_code_status_exists_in_the_database(db):
    rows = {r.key: r for r in db.execute(select(TicketStatus)).scalars()}
    code = {s.key: s for s in workflow.STATUSES}
    assert set(rows) == set(code), (
        f"코드의 상태 어휘와 DB 가 다르다 — 코드 {sorted(code)} · DB {sorted(rows)}"
    )
    for key, spec in code.items():
        row = rows[key]
        assert row.label == spec.label, f"{key} 의 라벨이 코드와 다르다"
        assert row.category == spec.category, f"{key} 의 집계 갈래가 코드와 다르다"
        assert row.sort_order == spec.sort_order, f"{key} 의 열 순서가 코드와 다르다"
        assert bool(row.is_default) is spec.is_default, f"{key} 의 기본값이 코드와 다르다"


def test_exactly_one_default_status(db):
    defaults = [r.key for r in db.execute(select(TicketStatus)).scalars() if r.is_default]
    assert defaults == [workflow.DEFAULT_STATUS], (
        f"새 티켓의 시작 상태가 하나가 아니다: {defaults}"
    )


def test_migration_literals_match_the_code_tables():
    """마이그레이션 **파일의 리터럴**이 코드와 같은가.

    위 시험들은 「마이그레이션을 돌린 DB」를 본다. 그 DB 는 시험 세션이 한 번 만든
    것이라, 이미 설치된 곳에 대해서는 아무 말도 하지 않는다. 파일을 직접 읽어야
    「이 파일이 심을 값」과 코드가 같다고 말할 수 있다.
    """
    src = MIGRATION.read_text(encoding="utf-8")

    statuses = re.findall(
        r'\(\s*"([^"]+)",\s*"([^"]+)",\s*"([A-Z_]+)",\s*(\d+),\s*(True|False)\s*\)', src
    )
    assert len(statuses) == len(workflow.STATUSES), (
        f"마이그레이션에서 상태 {len(statuses)}개를 읽었다 — 검사가 헛돈다"
    )
    from_file = {
        key: (label, category, int(order), flag == "True")
        for key, label, category, order, flag in statuses
    }
    from_code = {
        s.key: (s.label, s.category, s.sort_order, s.is_default) for s in workflow.STATUSES
    }
    assert from_file == from_code, (
        "마이그레이션 리터럴과 `app/work/workflow.py::STATUSES` 가 다르다"
    )


def test_the_vocabulary_endpoint_serves_the_table(client, login_as, db):
    """폼 드롭다운이 받는 목록이 **칸반 열과 같은 표**에서 나오는가.

    두 화면이 서로 다른 곳에서 어휘를 받으면 언젠가 한쪽에만 있는 상태가 생기고,
    그 상태의 티켓은 판에 안 나타난다. 그리고 아무도 안 읽는 표는 시드가 틀려도
    아무 일이 안 일어나므로, 시드를 맞물어 두는 위 시험들도 함께 헛돈다.
    """
    token = login_as("user", email="status-vocab@goodmit.co.kr")
    body = client.get("/api/work/statuses", headers={"X-CSRF-Token": token}).json()

    rows = db.execute(
        select(TicketStatus).order_by(TicketStatus.sort_order, TicketStatus.key)
    ).scalars().all()
    assert [s["key"] for s in body["statuses"]] == [r.key for r in rows], (
        f"응답 목록이 표와 다르다: {[s['key'] for s in body['statuses']]}"
    )
    assert body["default"] == workflow.DEFAULT_STATUS
    assert set(body["categories"]) == set(workflow.CATEGORIES)
    assert all("terminal" in s for s in body["statuses"]), "프론트가 종료 여부를 하드코딩하지 않으려면 terminal 이 있어야 한다"
    assert {s["key"] for s in body["statuses"] if s["terminal"]} == {
        s.key for s in workflow.STATUSES if workflow.is_terminal(s.key)
    }


def test_category_sql_and_row_renderers_agree(db):
    """두 표현이 **같은 답**을 내는가 (D-231 이 배운 것).

    `category_of`(행)와 `category_sql`(SQL)은 같은 표에서 만들어지지만, 「만들어졌다」와
    「같은 답을 낸다」는 다른 말이다. 실제로 실행해서 대조한다 — 모르는 값까지 포함해서.
    """
    from app.tickets.models import Ticket

    probes = [s.key for s in workflow.STATUSES] + ["없는상태", None]
    expression = workflow.category_sql(Ticket.status)
    for status in probes:
        # 리터럴을 태워 SQL 쪽 답을 얻는다. 행이 없어도 CASE 는 계산된다.
        sql_answer = db.execute(
            select(workflow.category_sql(__literal(status)))
        ).scalar_one()
        assert sql_answer == workflow.category_of(status), (
            f"«{status}» 에서 두 표현이 갈렸다 — SQL {sql_answer} · 행 "
            f"{workflow.category_of(status)}"
        )
    assert expression is not None


def __literal(value):
    from sqlalchemy import String, literal

    return literal(value, type_=String)
