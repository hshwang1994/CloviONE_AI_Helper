"""검색 결과에 범위를 건다 — **원본 목록과 같은 함수**를 쓴다 (0060 §25 · S5).

여기서 새 권한 규칙을 만들지 않는다. 목록 화면과 검색이 서로 다른 규칙을 쓰면, 목록에서
가려 둔 것이 검색에서 새거나(유출) 반대로 검색만 텅 비어 아무도 원인을 모른다.

## 0060 에서 바뀐 것 — 담당자 축을 버렸다

예전에는 검색 행이 `owner_user_ids`(담당자·작성자 집합)를 들고 부서 범위를 판정했다.
그 축은 원본과 다른 답을 낸다: 티켓 권한은 **프로젝트**가 정하고(0060), 문서 권한은
**Portal 이 정한 Ownership** 이 정한다. 그래서 색인 행이 원본의 Ownership 을 복사해 든다(0061).

## S5 에서 바뀐 것 — 판정이 이 파일에서 나갔다

소속 갈래도, 열람 제한(SEC-10) 판정도 이제 `app/authz/visibility.py` 한 곳이 만든다.
이 파일에 남은 것은 **어느 자원 종류로 물을 것인가** 하나뿐이다. 예전에는 소속은 공용
함수를 쓰면서 제한 판정만 여기 따로 있었고, 그래서 「같은 규칙」이라는 말이 절반만 사실이었다.

**상한 앞에서 걸어야 한다는 성질은 그대로다**(Z6). 범위 밖 행이 후보 상한
(`CANDIDATE_LIMIT`)을 채우면 내 범위 결과가 한 건도 안 남는다 — 오류가 아니라서 아무도
신고하지 않는다. `service.py` 가 이 절을 후보 질의 안에 넣는 이유다.
"""

from __future__ import annotations

from app.authz.visibility import (
    RESOURCE_SEARCH,
    VisibilityContext,
    effective_visibility_clause,
)


def sql_clause(ctx: VisibilityContext):
    """이 주체가 볼 수 있는 색인 행의 조건. ``None`` 이면 제한 없음(전역).

    소속 판정도 제한 문서 판정도 **여기서 만들지 않는다** — 목록·상세와 같은 함수
    (`app/authz/visibility.py::effective_visibility_clause`)가 만든다. 검색이 자기 규칙을
    따로 들고 있으면 목록에서 가려 둔 것이 검색에서 새거나(유출) 반대로 검색만 텅 빈다.

    ⚠️ 이 절은 **후보 상한 앞에서** 걸려야 한다(Z6) — `service.py` 의 `narrowing` 에 들어간다.
    """
    return effective_visibility_clause(ctx, RESOURCE_SEARCH)
