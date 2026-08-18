"""검색 인덱스 모델 (0030, PLAN Phase 5).

`search_documents` 는 검색 대상 한 건의 **평평한 사본**이다. 원본을 가리키는 포인터가 아니라
사본인 이유: 검색 한 번에 네 개 표를 조인하면 유형이 늘 때마다 쿼리를 고쳐야 하고, 정렬·
페이징이 유형별로 달라진다. 사본이면 검색은 표 하나만 보면 되고, 신선도는 워커가 책임진다.

FTS5(`search_index`)는 이 표를 `content=` 로 가리키는 external content 인덱스이고,
SQLite 트리거가 둘을 묶는다(마이그레이션 0030). 그래서 **이 ORM 으로 쓰기만 해도 인덱스가
따라온다** — 애플리케이션이 인덱스를 따로 갱신하지 않는다.

## v1 범위: 티켓 · 문서 · 게시판 · 사용자. 채팅은 제외한다

타협하지 않는다. 채팅을 넣으려면 방별 ACL(누가 그 방 멤버인가)을 인덱스 안에 넣어야 하고,
1:1 DM 을 공용 인덱스에 넣는 순간 그 인덱스를 잘못 읽는 코드 한 줄이 그대로 유출이 된다.
검색은 '조금 덜 찾아 주는' 실패는 견딜 수 있지만 '남의 DM 을 보여 주는' 실패는 못 견딘다.
`tests/security/test_search_no_chat.py` 가 보안 테스트로 못박는다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, OrgScopedMixin, UUIDPrimaryKeyMixin, utcnow
from app.core.ownership import (  # noqa: F401 — 색인 행이 그대로 재수출한다
    OWNER_DEPARTMENT,
    OWNER_ORGANIZATION,
    OWNER_PROJECT,
    OWNER_UNSET,
)

KIND_TICKET = "ticket"
KIND_DOCUMENT = "document"
KIND_BOARD = "board"
KIND_USER = "user"

# 인덱싱 대상 유형. **여기에 'chat' 을 추가하지 않는다**(모듈 docstring).
SEARCH_KINDS: tuple[str, ...] = (KIND_TICKET, KIND_DOCUMENT, KIND_BOARD, KIND_USER)

# 화면 그룹 제목. 백엔드가 들고 있는 이유는 유형이 늘 때 화면 세 곳(팔레트·결과화면·빈상태)을
# 따로 고치지 않게 하기 위해서다.
KIND_LABELS: dict[str, str] = {
    KIND_TICKET: "티켓",
    KIND_DOCUMENT: "문서",
    KIND_BOARD: "게시판",
    KIND_USER: "사용자",
}

# 워커/관측성에서 쓰는 컴포넌트 이름(observability.sync_status 의 PK).
COMPONENT_SEARCH = "search"


def join_owner_ids(user_ids) -> str:
    """소유자 id 집합을 저장 형태(",a,b,")로. 빈 집합은 빈 문자열이다.

    양끝을 콤마로 감싸는 이유는 나중에 SQL LIKE 로 좁힐 여지를 남겨 두기 위해서다
    (`%,uid,%` 가 접두 일치 사고를 안 낸다). 지금 판정은 파이썬에서 한다.
    """
    clean = [str(u).strip() for u in (user_ids or []) if str(u or "").strip()]
    # 순서를 고정한다 — 같은 내용인데 순서만 달라 인덱스가 매번 갱신되면 트리거가 헛돈다.
    unique = sorted(set(clean))
    return ("," + ",".join(unique) + ",") if unique else ""


def split_owner_ids(value: str | None) -> tuple[str, ...]:
    """저장 형태에서 소유자 id 집합으로."""
    return tuple(part for part in str(value or "").split(",") if part)


class SearchDocument(OrgScopedMixin, UUIDPrimaryKeyMixin, Base):
    """검색 대상 한 건."""

    __tablename__ = "search_documents"

    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # ",user-a,user-b," — 이 건에 **관여한 사람**들이다. 0060 이후로는 권한 판정에 쓰지
    # 않는다(아래 owner_* 세 컬럼이 판정한다). 남겨 두는 이유는 색인 행이 원본을 어떻게
    # 읽었는지 확인하는 유일한 흔적이고, 담당자 매핑 실패를 진단할 때 필요하기 때문이다.
    owner_user_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # ── Ownership (0061) — **원본과 같은 규칙으로** 상한 앞에서 거르기 위한 사본 ──────
    #
    # 검색은 원본 표를 조인하지 않는다(모듈 docstring 의 '평평한 사본'). 그래서 원본의
    # Ownership 을 색인 시점에 복사해 두고, 판정은 문서 목록이 쓰는 바로 그 함수
    # (`app/core/ownership.py::stored_ownership_clause`)에 넘긴다. 검색이 자기 규칙을
    # 갖는 순간 목록과 갈라지고, 갈라지는 방향 하나는 유출이다.
    #
    # 기본값이 `unset` 인 것은 fail-closed 다 — 색인이 Ownership 을 못 정하면 그 행은
    # 전역 관리자에게만 보인다.
    owner_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=OWNER_UNSET, server_default=OWNER_UNSET,
    )
    owner_dept_id: Mapped[str | None] = mapped_column(String(36))
    owner_project_id: Mapped[str | None] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    subtitle: Mapped[str | None] = mapped_column(String(300))
    route: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    url: Mapped[str | None] = mapped_column(String(1000))
    sort_key: Mapped[str | None] = mapped_column(String(40))
    indexed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
