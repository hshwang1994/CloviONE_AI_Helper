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
    # ",user-a,user-b," — 부서 범위 판정 전용. app/core/scope.py::any_assignee_visible 이
    # 이 집합 하나로 '다중 담당자 티켓은 담당자 전원의 부서에 보인다'를 처리한다.
    owner_user_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    subtitle: Mapped[str | None] = mapped_column(String(300))
    route: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    url: Mapped[str | None] = mapped_column(String(1000))
    sort_key: Mapped[str | None] = mapped_column(String(40))
    indexed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
