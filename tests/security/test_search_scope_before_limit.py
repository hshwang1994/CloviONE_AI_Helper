"""검색 후보 상한(400)이 **범위 필터보다 먼저** 걸리면 안 된다 (Z6).

## 무엇이 잘못됐나

`app/search/service.py` 는 인덱스에서 **전역 상위 400건**을 먼저 뽑고, 그 400건 안에서만
범위를 걸렀다. 부서 범위 관리자가 검색하면 상한을 채운 400건이 전부 남의 부서 것이라
**자기 부서 결과가 한 건도 안 남는다.** 오류도 빈 화면도 아니고 "결과가 거의 없다" +
truncated 배지라, 사용자는 "검색이 원래 이런가 보다" 하고 넘어간다.

## 이 테스트가 왜 이렇게 생겼나

⚠️ **범위 밖 데이터가 상한을 채우는 표본이라야 뜻이 있다.** 범위 밖이 400건 미만이면
고치기 전에도 통과한다 — 그건 테스트가 약한 게 아니라 표본이 사건을 재현하지 못하는 것이다.
그래서 범위 밖 잡음을 `CANDIDATE_LIMIT` 보다 많이 심는다.

그리고 **대상 문서가 상한 밖으로 밀리는 것까지 결정적으로** 만든다:

  * FTS 경로: 순서는 bm25(`ORDER BY rank`)다. 대상 문서만 본문을 길게 만들면 같은 낱말을
    가져도 점수가 나빠져 **꼴찌**가 된다(실측 확인: 501건 중 500번째).
  * LIKE 경로(1~2자): 순서는 `sort_key DESC` 다. 잡음의 sort_key 를 크게 주면 대상이 뒤로
    밀린다.

두 경로 모두 상한을 먼저 걸면 대상이 사라지고, 범위를 질의로 내리면 살아난다.

## 0060 이후 — 축이 담당자에서 **Ownership** 으로 바뀌었다

이 파일이 지키는 성질(범위를 상한 앞에서 건다)은 그대로다. 바뀐 것은 "무엇이 범위인가"
뿐이다: 색인 행은 이제 담당자 집합이 아니라 원본의 Ownership 을 들고, 티켓은 프로젝트가
소속을 정한다(0060 §11). 그래서 표본도 프로젝트로 갈라 심는다 — 우리팀 프로젝트 티켓
하나와 남의팀 프로젝트 티켓 500건이다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.search.models import (
    KIND_TICKET,
    OWNER_PROJECT,
    OWNER_UNSET,
    SearchDocument,
)
from app.search.service import CANDIDATE_LIMIT

pytestmark = pytest.mark.security

PASSWORD = "Str0ng-Passw0rd!"
NOW = datetime(2026, 8, 3, 9, 0, 0)

D_MINE = "dept-mine-0001"
D_OTHER = "dept-other-001"

# 범위 밖 잡음 건수. 상한보다 많아야 "상한을 범위 밖이 채운다"가 재현된다.
NOISE = CANDIDATE_LIMIT + 100

TARGET_TITLE = "우리팀 회의록 정리"
NOISE_TITLE = "남의팀 회의록 정리"


@pytest.fixture()
def world(db, make_user, make_project):
    """부서 둘 + 각 팀 프로젝트 + 우리 팀만 보는 부서 범위 관리자.

    티켓의 소속은 **프로젝트가 정한다**(0060). 그래서 부서마다 프로젝트를 하나씩 두고,
    색인 행은 그 프로젝트를 가리킨다.
    """
    db.add_all([
        Department(id=D_MINE, name="우리팀", org_id=DEFAULT_ORG_ID),
        Department(id=D_OTHER, name="남의팀", org_id=DEFAULT_ORG_ID),
    ])
    db.commit()

    mine = make_user("z6-mine@goodmit.co.kr", role="user", display_name="우리팀사람")
    other = make_user("z6-other@goodmit.co.kr", role="user", display_name="남의팀사람")
    boss = make_user("z6-boss@goodmit.co.kr", role="admin", display_name="우리팀관리자")
    mine.department_id = D_MINE
    mine.org_id = DEFAULT_ORG_ID
    other.department_id = D_OTHER
    other.org_id = DEFAULT_ORG_ID
    boss.department_id = D_MINE
    boss.org_id = DEFAULT_ORG_ID
    boss.admin_scope = "dept"
    boss.scope_dept_id = D_MINE
    boss.scope_org_id = DEFAULT_ORG_ID
    mine_project = make_project(name="우리팀 프로젝트", dept=D_MINE)
    other_project = make_project(name="남의팀 프로젝트", dept=D_OTHER)
    db.commit()
    return {
        "mine": mine.id, "other": other.id, "boss_email": boss.email,
        "mine_project": mine_project.id, "other_project": other_project.id,
    }


@pytest.fixture()
def corpus(db, world):
    """범위 밖 문서가 후보 상한을 통째로 채운 코퍼스."""
    rows = []
    for i in range(NOISE):
        rows.append(
            SearchDocument(
                kind=KIND_TICKET,
                ref_id=f"z6-noise-{i:04d}",
                org_id=DEFAULT_ORG_ID,
                owner_kind=OWNER_PROJECT,
                owner_project_id=world["other_project"],
                title=NOISE_TITLE,
                body="회의록",
                # LIKE 경로에서 잡음이 먼저 오게 한다(정렬은 sort_key DESC).
                sort_key="2026-08-03T09:00:00",
                route=f"/tickets/z6-noise-{i:04d}",
                indexed_at=NOW,
            )
        )
    rows.append(
        SearchDocument(
            kind=KIND_TICKET,
            ref_id="z6-target",
            org_id=DEFAULT_ORG_ID,
            owner_kind=OWNER_PROJECT,
            owner_project_id=world["mine_project"],
            title=TARGET_TITLE,
            # 본문이 길면 bm25 점수가 나빠져 FTS 순위에서 꼴찌가 된다.
            body="회의록 " + ("잡담 " * 200),
            sort_key="2000-01-01T00:00:00",
            route="/tickets/z6-target",
            indexed_at=NOW,
        )
    )
    db.add_all(rows)
    db.commit()
    return rows


def _login(client, email):
    response = client.post("/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _titles(client, query: str) -> set[str]:
    response = client.get("/api/search", params={"q": query})
    assert response.status_code == 200, response.text
    body = response.json()
    return {item["title"] for group in body["groups"] for item in group["items"]}


def test_fts_search_still_finds_my_departments_ticket(client, world, corpus):
    """범위 밖 500건이 상한을 채워도 내 부서 티켓은 결과에 있어야 한다."""
    _login(client, world["boss_email"])
    titles = _titles(client, "회의록")
    assert TARGET_TITLE in titles, (
        "범위 밖 문서가 후보 상한을 채워 내 부서 결과가 통째로 사라졌다 "
        f"(받은 제목: {sorted(titles)})"
    )
    assert NOISE_TITLE not in titles, "범위 밖 문서가 결과에 섞였다"


def test_like_fallback_still_finds_my_departments_ticket(client, world, corpus):
    """1~2자 LIKE 폴백도 같은 함정을 갖는다 — 상한이 정렬 뒤에 걸린다."""
    _login(client, world["boss_email"])
    titles = _titles(client, "회의")
    assert TARGET_TITLE in titles, (
        "LIKE 폴백에서도 범위 밖 문서가 상한을 채워 내 부서 결과가 사라졌다 "
        f"(받은 제목: {sorted(titles)})"
    )


def test_truncated_badge_is_not_a_lie_for_a_scoped_admin(client, world, corpus):
    """내 범위 안 일치가 한 건뿐이면 '더 있다'라고 말하면 안 된다.

    범위를 나중에 거르면 truncated 는 '전역 400건에 걸렸다'는 뜻이라 항상 켜진다 —
    사용자에게는 "더 있는데 안 보여 준다"로 읽히는데 사실은 볼 것이 그것뿐이다.
    """
    _login(client, world["boss_email"])
    body = client.get("/api/search", params={"q": "회의록"}).json()
    assert body["total"] == 1, f"내 범위 일치는 1건인데 {body['total']}건으로 셌다"
    assert body["truncated"] is False, (
        "범위 안에 더 볼 것이 없는데 truncated 배지가 떴다"
    )


def test_a_row_whose_owner_could_not_be_resolved_stays_closed(client, world, db):
    """소속을 못 정한 색인 행은 **아무에게도 안 보인다**(전역 관리자 제외).

    예전 축(담당자 집합)에서 같은 자리를 지키던 시험은 저장 문자열 모양(`,a,b,`)을 믿고
    좁히면 행이 조용히 사라진다는 것이었다. 0060 이 그 문자열 판정을 컬럼 판정으로 바꾸면서
    위험의 모양도 바뀌었다: 이제 위험한 것은 **`unset` 이 어느 갈래엔가 걸리는 것**이다.

    `unset` 은 "판정할 수 없음" 이고, 판정할 수 없으면 닫는 것이 0060 의 규칙이다. 여기가
    느슨해지면 소속 없는 티켓·문서가 검색을 통해 조직 전체에 열린다 — 목록에서는 닫혀
    있으므로 아무도 알아채지 못한다.
    """
    db.add(SearchDocument(
        kind=KIND_TICKET,
        ref_id="z6-unset",
        org_id=DEFAULT_ORG_ID,
        owner_kind=OWNER_UNSET,
        title="소속 미지정 회의록",
        body="회의록 본문",
        route="/tickets/z6-unset",
        indexed_at=NOW,
    ))
    db.commit()

    _login(client, world["boss_email"])
    assert "소속 미지정 회의록" not in _titles(client, "회의록"), (
        "Ownership 미지정 행이 부서 범위 관리자에게 새어 나갔다"
    )



def test_the_unresolved_row_is_still_reachable_by_a_global_admin(
    client, world, db, make_user
):
    """미지정 행이 **아무 데서도 안 보이면** 고칠 수도 없다.

    fail-closed 는 "관리자가 진단하고 지정할 수 있다" 를 전제로 성립한다. 전역까지 닫으면
    그 행은 존재하지만 어디서도 찾을 수 없는 상태가 된다 — 그건 보안이 아니라 유실이다.
    """
    db.add(SearchDocument(
        kind=KIND_TICKET, ref_id="z6-unset-2", org_id=DEFAULT_ORG_ID,
        owner_kind=OWNER_UNSET, title="미지정이지만 찾을 수는 있어야 하는 회의록",
        body="회의록 본문", route="/tickets/z6-unset-2", indexed_at=NOW,
    ))
    db.commit()
    make_user("z6-god3@goodmit.co.kr", role="system_admin", display_name="전역관리자3")
    _login(client, "z6-god3@goodmit.co.kr")
    assert "미지정이지만 찾을 수는 있어야 하는 회의록" in _titles(client, "회의록")


def test_global_admin_still_sees_everything(client, world, corpus, make_user):
    """범위를 질의로 내리면서 전역 관리자가 잃는 것은 없어야 한다."""
    make_user("z6-god@goodmit.co.kr", role="system_admin", display_name="전역관리자")
    _login(client, "z6-god@goodmit.co.kr")
    body = client.get("/api/search", params={"q": "회의록"}).json()
    titles = {item["title"] for group in body["groups"] for item in group["items"]}
    assert NOISE_TITLE in titles, "전역 관리자가 전역 결과를 잃었다"
