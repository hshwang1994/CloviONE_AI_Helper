"""`0001_pg_baseline` 이 심는 부트스트랩 행이 앱이 기대하는 그 값인가 (D-189).

마이그레이션은 **얼어붙은 스냅숏**이라 앱 상수를 import 하지 않는다 — 그래서 고정 id 가
두 곳에 적혀 있다. 두 곳에 적힌 값은 반드시 어긋난다(`app/org/constants.py` 가 그 사실을
자기 docstring 에 적어 두고 있다). 어긋나면 증상은 이렇게 나온다:

  * 조직 id 가 다르면 — 거의 모든 표의 `org_id` 기본값이 없는 조직을 가리켜 **첫 INSERT 부터**
    FK 위반이다. 앱은 뜨는데 아무것도 못 만든다.
  * 전체 채팅방 id 가 다르면 — 채팅 화면이 빈 화면으로 열리고 오류는 안 난다.
  * 싱글턴 id 가 다르면 — 첫 동기화가 행을 하나 더 만들고, 그 뒤로 상태 화면이 둘 중
    아무거나 보여 준다.

셋 다 "고장났다" 가 아니라 "이상하다" 로 보이는 실패라, 여기서 못박는다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import select

from app.org.constants import DEFAULT_ORG_ID, DEFAULT_ORG_NAME, DEFAULT_ORG_SLUG, ORG_ACTIVE
from app.org.models import Organization
from app.team_chat.models import GLOBAL_ROOM_ID, ChatRoom
from app.tickets.models import META_CACHE_ID, SYNC_STATE_ID, TicketMetaCache, TicketSyncState

BASELINE = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0001_pg_baseline.py"


def _baseline_module():
    """기준선 revision 을 모듈로 읽는다(실행하지 않는다) — 상수만 본다."""
    spec = importlib.util.spec_from_file_location("_pg_baseline", BASELINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_constants_match_the_app_constants():
    """두 곳에 적힌 고정 id 가 같은가. 이 시험이 그 둘을 맞물려 둔다."""
    m = _baseline_module()
    assert m._DEFAULT_ORG_ID == DEFAULT_ORG_ID
    assert m._DEFAULT_ORG_SLUG == DEFAULT_ORG_SLUG
    assert m._DEFAULT_ORG_NAME == DEFAULT_ORG_NAME
    assert m._GLOBAL_CHAT_ROOM_ID == GLOBAL_ROOM_ID
    assert m._TICKET_SINGLETON_ID == SYNC_STATE_ID == META_CACHE_ID


def test_organization_name_is_the_company_not_the_product():
    """조직 이름 자리에 제품명이 들어가면 안 된다.

    0034 가 리브랜딩하면서 실제로 이 실수를 했고(조직명 = "ClovirAssist"), 화면에 조직
    이름이 나오는 자리마다 회사 이름 대신 제품 이름이 찍혔다. 0038 이 기존 행을 고쳤지만
    **시드 상수를 안 고치면 다음 새 설치에서 되살아난다** — 여기가 그 자리다.
    """
    m = _baseline_module()
    assert "Clovir" not in m._DEFAULT_ORG_NAME


def test_default_organization_row_exists(db):
    """기본 조직 행이 실제로 있는가 — 없으면 `org_id` FK 를 가진 모든 표가 못 쓴다."""
    org = db.execute(
        select(Organization).where(Organization.id == DEFAULT_ORG_ID)
    ).scalar_one()
    assert org.slug == DEFAULT_ORG_SLUG
    assert org.name == DEFAULT_ORG_NAME
    assert org.status == ORG_ACTIVE


def test_global_chat_room_exists(db):
    room = db.execute(select(ChatRoom).where(ChatRoom.id == GLOBAL_ROOM_ID)).scalar_one()
    assert room.is_global is True
    assert room.event_seq == 0


def test_ticket_singletons_exist(db):
    """싱글턴이 **정확히 하나씩** 있어야 한다 — 둘이면 상태 화면이 아무거나 보여 준다."""
    sync = db.execute(select(TicketSyncState)).scalars().all()
    meta = db.execute(select(TicketMetaCache)).scalars().all()
    assert [r.id for r in sync] == [SYNC_STATE_ID]
    assert [r.id for r in meta] == [META_CACHE_ID]
    assert sync[0].ticket_count == 0
    assert meta[0].projects_json == "[]"
