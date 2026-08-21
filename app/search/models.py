"""검색 인덱스 모델 (0030, PLAN Phase 5).

`search_documents` 는 검색 대상 한 건의 **평평한 사본**이다. 원본을 가리키는 포인터가 아니라
사본인 이유: 검색 한 번에 네 개 표를 조인하면 유형이 늘 때마다 쿼리를 고쳐야 하고, 정렬·
페이징이 유형별로 달라진다. 사본이면 검색은 표 하나만 보면 되고, 신선도는 워커가 책임진다.

검색은 이 표 **하나**만 본다. 예전에는 FTS5 가상 표(`search_index`)가 옆에 있고 SQLite
트리거가 둘을 묶었다 — PG 에는 그 문법이 없고, 필요도 없다: `gin_trgm_ops` 인덱스가
`title`·`body` 컬럼에 직접 걸리므로 **이 ORM 으로 쓰기만 해도 인덱스가 따라온다.**
트리거로 지키던 성질을 인덱스가 공짜로 준다(D-209 · `app/search/query.py`).

## v1 범위: 티켓 · 문서 · 게시판 · 사용자. 채팅은 제외한다

타협하지 않는다. 채팅을 넣으려면 방별 ACL(누가 그 방 멤버인가)을 인덱스 안에 넣어야 하고,
1:1 DM 을 공용 인덱스에 넣는 순간 그 인덱스를 잘못 읽는 코드 한 줄이 그대로 유출이 된다.
검색은 '조금 덜 찾아 주는' 실패는 견딜 수 있지만 '남의 DM 을 보여 주는' 실패는 못 견딘다.
`tests/security/test_search_no_chat.py` 가 보안 테스트로 못박는다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
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
    __table_args__ = (
        # **후보 생성의 정본**(D-209). `ILIKE '%…%'` 를 이 인덱스가 받는다 —
        # `app/search/query.py` 가 만드는 조건이 전부 그 모양이다.
        #
        # 한국어에서 이것 말고 다른 선택지가 없다는 것을 S1 이 실 PG16 에서 쟀다:
        # 어절 내부 부분일치 질의 20건 중 전문검색(`to_tsvector('simple')`)은 **19건이
        # 아무것도 못 찾았고**(recall 0.083), `gin_trgm_ops` 는 **recall 1.000** 에
        # seqscan 보다 80배 빨랐다.
        #
        # 제목과 본문을 따로 거는 이유: 조건이 `title ILIKE … OR body ILIKE …` 라
        # PG 가 두 인덱스를 각각 타고 BitmapOr 로 합친다. 이어 붙인 한 컬럼에 걸면
        # 제목 가중치(`query.rank_expression`)를 줄 수 없다.
        #
        # ⚠️ **플래너가 항상 이 인덱스를 고르지는 않는다.** PG 는 `ILIKE '%…%'` 의
        # 선택도를 추정하지 못해 «거의 다 걸린다»로 본다(실측: 20,000행에서 추정
        # 19,998 · 실제 435). 그래서 작은 표에서는 seq scan 을 고르고, 그건 **틀린
        # 판단이 아니다** — 현 색인 규모(1~2천 행)에서 seq scan 은 3ms 다(D-209).
        #
        # 코퍼스가 자란 뒤 검색이 느려지면 **인덱스를 의심하지 말고 통계·비용
        # 파라미터를 본다.** 인덱스 자체는 이 조건을 받는다(강제하면 6.4ms 대 23.7ms).
        # 원장: `docs/platform/EVIDENCE/S2/search_gin_index_is_usable.txt`
        Index(
            "ix_search_documents_title_trgm", "title",
            postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "ix_search_documents_body_trgm", "body",
            postgresql_using="gin", postgresql_ops={"body": "gin_trgm_ops"},
        ),
    )

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
