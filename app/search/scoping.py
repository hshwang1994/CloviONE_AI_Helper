"""검색 결과에 범위를 건다 — **원본 목록과 같은 함수**를 쓴다 (0060 §25).

여기서 새 권한 규칙을 만들지 않는다. 목록 화면과 검색이 서로 다른 규칙을 쓰면, 목록에서
가려 둔 것이 검색에서 새거나(유출) 반대로 검색만 텅 비어 아무도 원인을 모른다.

## 0060 에서 바뀐 것 — 담당자 축을 버렸다

예전에는 검색 행이 `owner_user_ids`(담당자·작성자 집합)를 들고 부서 범위를 판정했다.
그 축은 이제 원본과 다른 답을 낸다:

  * 티켓 권한은 **프로젝트**가 정한다(0060). 담당자가 없는 티켓도 프로젝트 ACL 안에서
    정상으로 보이는데, 담당자 축은 그 티켓을 "소유자 0명" 으로 읽고 닫아 버렸다.
  * 문서 권한은 **Portal 이 정한 Ownership** 이 정한다. 작성자 축은 사람이 부서를 옮기면
    문서가 따라 움직인다 — 목록은 안 움직이는데 검색만 움직였다.

그래서 색인 행이 원본의 Ownership 을 복사해 들고(0061), 판정은 문서 목록이 쓰는 바로 그
함수 하나로 한다:

    app/core/ownership.py::stored_ownership_clause

`unset` 은 어느 갈래에도 안 걸린다 — 색인이 소속을 못 정한 행은 전역 관리자만 본다
(fail-closed). 이게 "판정할 수 없으면 닫는다" 를 검색에서도 지키는 자리다.

## 왜 SQL 한 절로 끝나는가 (파이썬 2차 판정이 없다)

예전에는 SQL 로 좁힌 뒤 파이썬에서 한 번 더 걸렀다. 담당자 집합 판정이 문자열 안에
들어 있어 SQL 로 정확히 쓰기 어려웠기 때문이다. Ownership 은 컬럼 세 개라 SQL 이 정확히
같은 판정을 할 수 있고, 두 벌로 두면 오히려 갈라진다.

**상한 앞에서 걸어야 한다는 성질은 그대로다**(Z6). 범위 밖 행이 후보 상한
(`CANDIDATE_LIMIT`)을 채우면 내 범위 결과가 한 건도 안 남는다 — 오류가 아니라서 아무도
신고하지 않는다. `service.py` 가 이 절을 후보 질의 안에 넣는 이유다.
"""

from __future__ import annotations

from sqlalchemy import or_, select

from app.core.ownership import stored_ownership_clause
from app.core.scope import Scope
from app.search.models import KIND_DOCUMENT, SearchDocument


def sql_clause(scope: Scope):
    """이 범위가 볼 수 있는 색인 행의 조건. ``None`` 이면 제한 없음(전역).

    조직 범위에서 `org_id` 를 따로 보지 않는 이유: `stored_ownership_clause` 의 조직·부서
    갈래가 이미 `org_id` 를 비교하고, 프로젝트 갈래는 프로젝트의 조직으로 좁힌다. 여기서
    한 번 더 `SearchDocument.org_id` 를 걸면 조건이 두 곳에 생기고, 둘 중 하나만 고치는
    날이 온다.
    """
    return stored_ownership_clause(
        scope,
        kind_col=SearchDocument.owner_kind,
        org_col=SearchDocument.org_id,
        dept_col=SearchDocument.owner_dept_id,
        project_col=SearchDocument.owner_project_id,
    )


def not_restricted_clause():
    """열람 제한 문서(SEC-10)를 결과에서 뺀다. 색인 1층과 짝이 되는 2층이다.

    ## 왜 두 층인가

    색인기가 제한 문서를 애초에 안 담지만(`app/search/indexer.py::_document_rows`), 색인은
    주기 작업이다(기본 300초, `notion_docs_sync_interval_seconds` 와 같은 계열). 운영자가
    제한을 **켠 직후** 다음 색인이 돌기 전까지 창이 열린다 — 그 창이 정확히 "지금 막
    민감하다고 판단한 문서"의 창이라 가장 위험하다. 질의 단계에도 같은 판정을 둬서 닫는다.

    ## 왜 예외(작성자·운영자)가 없는가

    목록·상세에서는 작성자와 운영자군이 제한 문서를 본다(`doc_in_scope`). 여기서는 **아무도
    검색으로 찾지 못한다** — 검색 색인은 범위가 없는 전역 저장소라, 예외를 하나 열면 그
    예외가 인덱스 안 ACL 의 시작이 된다(채팅을 통째로 안 담는 것과 같은 이유). 기능은
    잃지 않는다: 그 사람들은 문서 목록에서 그대로 보고 연다.

    ⚠️ 이 절은 **후보 상한 앞에서** 걸려야 한다(Z6) — `service.py` 의 `narrowing` 에 들어간다.
    """
    from app.team_docs.models import DocumentCache

    restricted_refs = select(DocumentCache.notion_page_id).where(
        DocumentCache.restricted.is_(True)
    )
    # 문서 유형에만 건다 — 티켓·게시글·사용자 행의 ref_id 가 우연히 겹칠 이유는 없지만,
    # 조건을 유형으로 좁혀 두면 이 절이 다른 유형의 결과를 조용히 줄일 길 자체가 없다.
    return or_(
        SearchDocument.kind != KIND_DOCUMENT,
        SearchDocument.ref_id.not_in(restricted_refs),
    )
