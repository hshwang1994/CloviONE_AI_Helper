"""옛 문서 미러(`document_cache`)와 그 동기화 상태.

**여기 있는 것은 옛 미러다** (S14 · D1). 문서의 정본은 `documents`(Knowledge Domain)이고
사용자에게 보이는 경로는 그쪽만 읽는다. 이 표는 이관 흔적과 소속(부서·프로젝트) 집계가
아직 참조하고 있어 남아 있을 뿐이고, 표를 내리는 것은 별도 작업이다.

사람이 문서에 남긴 것(댓글·즐겨찾기·최근 열람)은 `app/knowledge/models.py` 로 옮겼다.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (  # noqa: F401 — NAMES_SEP/join_names/split_names 재수출
    NAMES_SEP,
    Base,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    join_names,
    split_names,
    utcnow,
)

SYNC_IDLE = "idle"
SYNC_RUNNING = "running"
SYNC_OK = "ok"
SYNC_ERROR = "error"

# 다중값 relation 이름들을 한 컬럼에 담는 구분자(sentinel-wrapped Unit Separator)와 그 헬퍼는
# ticket_cache 도 똑같이 써야 해서 정의를 app/core/models_base.py 로 올렸다. 여기서는 그대로
# 재수출한다 — 기존 import 경로(app.team_docs.models.join_names 등)는 하나도 바뀌지 않는다.

# DocumentSyncState 는 단일 행이다 — 이 고정 id로 upsert 한다.
SYNC_STATE_ID = "documents"

# 문서가 저장할 수 있는 소유 종류 (0060). 어휘의 정본은 `app/core/ownership.py` 이고
# 여기서는 그중 **문서가 실제로 저장하는 넷**만 다시 노출한다(personal/membership/global 은
# 문서에 해당하지 않는다). 판정은 저장하는 쪽이 아니라 ownership 모듈이 한다.
from app.core.ownership import (  # noqa: E402 — 어휘 재수출(정의는 ownership 한 곳)
    OWNER_DEPARTMENT,
    OWNER_ORGANIZATION,
    OWNER_PROJECT,
    OWNER_UNSET,
)

DOC_OWNER_KINDS: tuple[str, ...] = (
    OWNER_PROJECT, OWNER_DEPARTMENT, OWNER_ORGANIZATION, OWNER_UNSET,
)


class DocumentCache(OrgScopedMixin, UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_cache"

    # ── Portal 이 소유하는 소속 (0060) ────────────────────────────────────────
    #
    # **외부 소스(Notion)에 조직 컬럼을 요구하지 않는다.** 저쪽은 콘텐츠의 정본이고
    # "이 문서가 어느 부서/프로젝트 것인가" 는 Portal 이 정본이다. 그래서 이 세 컬럼은
    # `app/team_docs/sync.py::_upsert` 가 **절대 건드리지 않는다** — `restricted`(0057)·
    # `classification_manual`(0018)과 같은 자리다. 소스가 다른 시스템으로 교체돼도
    # 조직 권한 모델을 다시 설계할 필요가 없어야 한다는 것이 이 배치의 목적이다.
    #
    # 작성자(`author_notion_ids`)와 소유는 **다른 개념**이다. 작성자가 다른 부서로 옮겨도
    # 그 사람이 예전에 쓴 문서가 따라 움직이면 안 된다.
    owner_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=OWNER_UNSET,
        server_default=OWNER_UNSET, index=True,
    )
    # 부서 소유일 때의 부서 id. **이름이 아니라 id** — 부서명이 바뀌거나 상위 부서가
    # 새로 생겨도 연결이 끊기지 않아야 한다.
    owner_dept_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("org_units.id"), nullable=True, index=True
    )
    # 프로젝트 소유일 때의 Portal 프로젝트 id. Notion relation **이름**이 아니라 id 로
    # 잇는다 — 이름은 바뀌고 중복될 수 있어 장기 키가 될 수 없다.
    owner_project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True, index=True
    )

    notion_page_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    # 낙관적 잠금 (S6). 티켓·프로젝트와 **같은 이름의 같은 규약**이다 — 세 화면이 같은
    # 충돌을 서로 다른 필드 이름으로 다루면 프런트가 세 벌의 처리를 갖게 되고, 그중
    # 하나가 빠진 화면에서 덮어쓰기가 조용히 일어난다.
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    url: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # relation 이름들은 콤마로 합쳐 저장(표시·검색용). 필터 매칭은 콤마 분리로 처리.
    type_names: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category_names: Mapped[str] = mapped_column(Text, nullable=False, default="")
    project_names: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 외부 소스 relation의 **id** 미러 (0060). `project_names` 는 표시용이고 이쪽이
    # 식별용이다 — 이름은 바뀌고 중복될 수 있어 무엇과 연결할지 정하는 키가 될 수 없다.
    # 이 컬럼은 콘텐츠 미러라 sync 가 소유한다(위 owner_* 세 컬럼과 반대다).
    project_external_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str | None] = mapped_column(String(64), index=True)
    priority: Mapped[str | None] = mapped_column(String(64))
    # 신규 택소노미(§17 개편) — 동기화 때 classify.py로 자동 계산. 사용자가 수동으로 고치면
    # classification_manual=True 가 되어 이후 sync가 덮어쓰지 않는다. type_names/category_names는
    # 원본(분류 입력)으로 남겨 두고, 화면은 아래 값을 보여준다. tech_tags는 NAMES_SEP-joined.
    document_type: Mapped[str | None] = mapped_column(String(32), index=True)
    work_field: Mapped[str | None] = mapped_column(String(32), index=True)
    tech_tags: Mapped[str] = mapped_column(Text, nullable=False, default="")
    classification_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 문서 단위 열람 제한(SEC-10). Notion 원본에 대응 필드가 없는 **순수 앱 측 플래그**라
    # classification_manual과 같은 이유로 sync._upsert가 절대 건드리지 않는다(건드리면 매
    # 재동기화마다 관리자가 건 제한이 조용히 풀린다 — 이 앱에서 이미 한 번 겪은 실수의 같은
    # 모양). True면 doc_in_scope가 운영자군/작성자 외에는 목록·상세 어디서도 이 문서를
    # 통과시키지 않는다(원본 Notion 콘텐츠 자체는 건드리지 않는 항목 단위 접근 통제).
    restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    author_names: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 작성자의 **소스 id**(0040 / X2). 이름 문자열로 권한을 판정하면 개명하면 자기 문서를
    # 못 지우고 동명이인은 남의 문서를 지운다 — `display_name` 에 유일 제약이 없기 때문이다.
    # 매핑(`user_notion_mappings`)을 거쳐 앱 사용자로 해석한다.
    author_notion_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    doc_date: Mapped[date | None] = mapped_column(Date)
    orig_date: Mapped[date | None] = mapped_column(Date)
    created_time: Mapped[datetime | None] = mapped_column(DateTime)
    last_edited: Mapped[datetime | None] = mapped_column(DateTime)
    original_url: Mapped[str | None] = mapped_column(String(1000))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    memo: Mapped[str] = mapped_column(Text, nullable=False, default="")
    has_files: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notion_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    # 포털에서 저장한 본문(0046). 읽기만 할 때는 캐시하지 않는 것이 맞았지만(모듈 docstring),
    # 편집을 열면 저장 순서가 '우리 DB 먼저 → Notion push' 여야 한다. 정본을 담을 자리가
    # 없으면 Notion 이 죽은 날 사용자가 방금 친 글이 통째로 사라진다.
    #
    # **NULL 과 빈 문자열은 다르다.** NULL 은 "아직 포털에서 고친 적이 없다"(원본이 정본)이고
    # 빈 문자열은 "본문을 비웠다" 이다. 둘을 뭉개면 동기화된 문서 전부가 빈 본문으로 보이고,
    # 그 상태에서 저장하면 원본 본문이 지워진다.
    body_markdown: Mapped[str | None] = mapped_column(Text)
    # 정본은 저장됐는데 원본에 못 밀어 넣은 상태면 그 이유. 토스트는 사라지지만 이 값은
    # 남으므로 다시 열어도 화면이 "저장됨, 원본 반영 실패" 를 말할 수 있다.
    body_sync_error: Mapped[str | None] = mapped_column(Text)
    body_synced_at: Mapped[datetime | None] = mapped_column(DateTime)


class DocumentSyncState(Base):
    __tablename__ = "document_sync_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # 항상 SYNC_STATE_ID
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SYNC_IDLE)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    doc_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 마지막 동기화가 **실제로 지운** 건수(드리프트 지표)였다. 미러 동기화가 사라진 뒤로
    # (S14 · D-284) 이 칸에 쓰는 코드가 없다 — 표를 내리는 것은 별도 migration 몫이라
    # 컬럼만 남아 있고, 값은 항상 0 이다.
    pruned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


# ── 여기 있던 세 표는 `app/knowledge/models.py` 로 옮겼다 (S14 · C2) ─────────
#
# `DocumentFavorite` · `DocumentComment` · `DocumentRecentView` 는 사람이 문서에 남긴
# 것이고, 문서의 정본이 `documents`(Knowledge Domain)로 넘어간 이상 그쪽에 붙어 있어야
# 한다. 옛 조회 키(`notion_page_id`)는 이 표(`document_cache`)를 가리켰는데, 그 표는
# 이제 사용자에게 보이는 어떤 경로도 읽지 않는 옛 미러다(D1).
