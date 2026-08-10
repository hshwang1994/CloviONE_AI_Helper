"""프로필 사진 서빙의 **면제 근거가 더 이상 사실이 아니다** (조직 축).

`GET /api/profile/avatar/{user_id}` 는 "이름·부서가 이미 전사 공개니 사진만 좁히면
목록에서 이름 옆 사진이 뚫린 채로 보인다" 는 이유로 전 직원 대상이었다. 그 전제가
조직 축에서는 깨졌다 — `/api/team-chat/directory` 는 이제 `org_id` 로 좁히고 게시판도
조직으로 좁는다. 즉 **다른 조직 사람은 애초에 목록에 안 나오는데** 사진만 `user_id`
하나로 그대로 나갔다. 목록에서 가린 것이 id 로 뚫리는, 이 저장소가 여러 번 겪은 모양이다.

얼굴 사진은 이름보다 더 개인적이다 — 다른 회사 사람의 얼굴을 id 열거로 긁어모을 수 있다.

**부서로는 좁히지 않는다.** 같은 조직 다른 팀 사람의 사진이 안 보이면 그건 기능 축소지
보안이 아니다. 디렉터리가 조직으로만 좁히는 것과 같은 축이어야 한다.

## 이 파일이 스스로를 의심하는 방법

사진 서빙은 404 가 나는 길이 **여러 개**다: 계정이 없다 / 보관됐다 / 사진이 없다 /
파일이 없다. 그래서 "404 가 나왔다" 만 보면 조직 판정이 없어도 초록불이 뜬다 —
가짜 안전감이다. 그래서 모든 테스트가 **같은 URL 이 조건 하나만 다를 때 200 이었음을
먼저 확인**한다. 막을 수 있는 것이 그 판정 하나뿐이 되게 만든 것이다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security

# 최소 PNG. 형식 판정은 확장자가 아니라 이 앞 8바이트가 한다(app/core/uploads.py).
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _upload_avatar_as(client, login_as, email: str) -> str:
    """그 사람으로 로그인해 사진을 올리고 서빙 URL 을 돌려준다.

    사진이 **실제로 있는** 상태를 만드는 것이 핵심이다 — 사진이 없으면 어차피 404 라
    조직 판정이 있든 없든 테스트가 통과해 버린다.
    """
    csrf = login_as("user", email=email)
    r = client.post(
        "/api/me/avatar",
        files={"file": ("me.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, f"사진 업로드가 실패하면 이 테스트는 아무것도 증명하지 못한다: {r.text}"
    url = r.json()["avatar_url"]
    assert url, "업로드는 됐다는데 서빙 URL 이 없다"
    # 올린 본인이 못 받으면 그 뒤의 404 는 조직 때문이 아니다.
    assert client.get(url).status_code == 200, "올린 본인도 자기 사진을 못 받는다"
    return url


def test_another_organizations_avatar_is_not_served(client, login_as, two_orgs):
    """다른 조직 사람의 프로필 사진이 user_id 하나로 나가면 안 된다.

    403 이 아니라 **404** 다 — 403 은 "그 id 는 존재한다" 를 알려 준다(저장소 규칙).
    """
    url = _upload_avatar_as(client, login_as, "orga@goodmit.co.kr")

    login_as("user", email="orgb@goodmit.co.kr")
    r = client.get(url)

    assert r.status_code == 404, (
        f"다른 조직 사람의 프로필 사진이 그대로 나간다({r.status_code}) — "
        "디렉터리·게시판은 조직으로 좁히는데 사진만 전사 공개다"
    )
    assert r.content != PNG_BYTES, "상태코드만 바뀌고 사진 원본이 그대로 나간다"


def test_a_teammate_in_another_department_still_gets_the_photo(
    client, login_as, two_orgs, make_user, db
):
    """오탐 방지 — **같은 조직 다른 팀**은 그대로 보여야 한다.

    부서로 좁히면 이름 옆 사진이 사내에서 뚫린 채로 보인다. 그건 이 게이트가 막으려던
    문제가 아니라 기능 축소다(디렉터리가 조직으로만 좁히는 것과 같은 판단).
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    other_team = Department(name="A팀2", org_id=DEFAULT_ORG_ID)
    db.add(other_team)
    db.flush()
    mate = make_user("orga2@goodmit.co.kr", role="user", display_name="A사람2")
    mate.org_id = DEFAULT_ORG_ID
    mate.department_id = other_team.id
    db.commit()

    url = _upload_avatar_as(client, login_as, "orga2@goodmit.co.kr")

    login_as("user", email="orga@goodmit.co.kr")
    r = client.get(url)

    assert r.status_code == 200, (
        f"같은 조직 다른 팀 사람의 사진이 안 보인다({r.status_code}) — 부서로 좁히면 안 된다"
    )
    assert r.content == PNG_BYTES


def test_an_archived_accounts_avatar_is_still_hidden(
    client, login_as, two_orgs, make_user, db
):
    """기존 성질 유지 — 보관된 계정의 사진은 같은 조직 사람에게도 안 나간다.

    조직 판정을 새로 끼워 넣으면서 보관 판정을 밀어내면, 퇴사자 얼굴이 다시 살아난다.
    """
    from app.core.models_base import utcnow
    from app.org.constants import DEFAULT_ORG_ID

    leaver = make_user("orga-leaver@goodmit.co.kr", role="user", display_name="퇴사자")
    leaver.org_id = DEFAULT_ORG_ID
    leaver.department_id = two_orgs.dept_a.id
    db.commit()

    url = _upload_avatar_as(client, login_as, "orga-leaver@goodmit.co.kr")

    login_as("user", email="orga@goodmit.co.kr")
    assert client.get(url).status_code == 200, "보관 전에는 보여야 한다 — 아니면 아래 404 는 무의미하다"

    leaver.archived_at = utcnow()
    db.commit()

    r = client.get(url)
    assert r.status_code == 404, f"보관된 계정의 사진이 나간다: {r.status_code}"
    assert r.content != PNG_BYTES


def test_a_deactivated_accounts_avatar_is_also_hidden(client, login_as, two_orgs, make_user, db):
    """SEC-05 — `active=False`(보관은 아니고 비활성화만 된 계정)도 archived와 같이 막혀야 한다.

    이 판정이 참조하는 team_chat/repository.py::directory() 는 "누가 보이는가"를
    active와 archived_at 둘 다로 정한다 — 사진만 archived_at 하나만 보면, 디렉터리에서
    이미 감춘 비활성 사용자의 얼굴이 URL로는 여전히 나가는 비대칭이 생긴다.
    """
    disabled = make_user("orga-disabled@goodmit.co.kr", role="user", display_name="비활성")
    disabled.org_id = two_orgs.org_a_id
    disabled.department_id = two_orgs.dept_a.id
    db.commit()

    url = _upload_avatar_as(client, login_as, "orga-disabled@goodmit.co.kr")

    login_as("user", email="orga@goodmit.co.kr")
    assert client.get(url).status_code == 200, "비활성화 전에는 보여야 한다 — 아니면 아래 404 는 무의미하다"

    disabled.active = False
    db.commit()

    r = client.get(url)
    assert r.status_code == 404, f"비활성화된 계정의 사진이 나간다: {r.status_code}"
    assert r.content != PNG_BYTES
