"""조직 축 — **두 조직이 실제로 존재하는 세계**에서만 의미가 있다 (7단계 #5).

계획서(PLAN4)가 못박은 것: 조직이 하나뿐이면 `WHERE org_id = :org` 는 한 행도 안 거르고
**걸린 것과 안 건 것이 구별되지 않는다**. 그래서 `two_orgs` 픽스처가 먼저 있어야 한다.

이 파일은 **먼저 세계가 제대로 만들어졌는지**를 확인하고(그게 틀리면 아래 모든 판정이
무의미하다), 그다음 조직 간 격리를 본다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security


def test_the_seed_really_makes_two_distinct_orgs(two_orgs, db):
    """전제 검증. 이게 틀리면 조직 격리 테스트는 전부 **아무것도 증명하지 못한다** —
    `test_scope_idor_matrix.py` 가 손으로 값을 대입해 만든 가짜 안전감과 같은 실패다."""
    from app.org.models import Organization

    assert two_orgs.org_a_id != two_orgs.org_b_id
    assert db.query(Organization).count() >= 2
    assert two_orgs.user_a.org_id == two_orgs.org_a_id
    assert two_orgs.user_b.org_id == two_orgs.org_b_id
    assert two_orgs.dept_a.org_id != two_orgs.dept_b.org_id


def test_org_scope_actually_filters_now(two_orgs, db):
    """`scope_filter` 가 **실제로 행을 거른다**. 조직이 하나일 때는 확인할 수 없던 것이다."""
    from sqlalchemy import select

    from app.core.scope import Scope, scope_filter
    from app.org.models import Department
    from app.users.models import ADMIN_SCOPE_ORG

    scope = Scope(kind=ADMIN_SCOPE_ORG, org_id=two_orgs.org_b_id)
    # `scope_filter` 는 **절(clause)** 을 돌려준다 — 전역이면 `None` 이다. 그 설계 덕에
    # "조건을 빼먹은 코드" 와 "조건이 항상 참인 코드" 가 눈으로 구별된다(그 파일 docstring).
    clause = scope_filter(scope, org_column=Department.org_id)
    assert clause is not None, "조직 범위인데 조건이 안 만들어졌다"
    names = {d.name for d in db.execute(select(Department).where(clause)).scalars().all()}

    assert "B팀" in names
    assert "A팀" not in names, "조직 범위가 다른 조직 부서를 거르지 못한다"


def test_a_user_scoped_to_org_b_cannot_reach_org_a_users(client, login_as, two_orgs, db):
    """관리자 범위를 조직 B 로 두면 조직 A 사람이 안 보여야 한다 —
    **F2 로 만든 설정 경로**로 넣고 확인한다(손으로 대입하지 않는다)."""
    from app.users.models import ROLE_ADMIN

    boss = two_orgs.user_b
    boss.role = ROLE_ADMIN
    db.commit()

    csrf = login_as("system_admin")
    r = client.patch(
        f"/api/admin/users/{boss.id}",
        json={"admin_scope": "org", "scope_org_id": two_orgs.org_b_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text

    login_as("admin", email="orgb@goodmit.co.kr")
    emails = {u["email"] for u in client.get("/api/admin/users").json()["items"]}

    assert "orgb@goodmit.co.kr" in emails, "자기 조직 사람이 안 보인다"
    assert "orga@goodmit.co.kr" not in emails, "다른 조직 사람이 보인다"


def test_the_board_does_not_cross_organizations(client, login_as, two_orgs, db):
    """자유게시판은 **사내** 공지판이다 — 다른 회사 글이 섞이면 안 된다 (1순위 유출 #4).

    부서로 좁히지 않는다(그러면 사내 공지판이 아니게 된다). 조직이 맞는 축이고,
    `Post` 는 `OrgScopedMixin` 을 이미 상속한다 — **모델은 선언했는데 질의가 안 걸었다.**

    조직이 하나뿐일 때는 이 테스트를 쓸 수 없었다: `WHERE org_id` 를 넣든 안 넣든 결과가
    같아서 **초록불이 아무것도 증명하지 못한다**(PLAN4). `two_orgs` 가 있어야 의미가 생긴다.
    """
    from app.board.models import Post

    db.add_all([
        Post(title="A조직 공지", body="a", category="공지", org_id=two_orgs.org_a_id,
             author_user_id=two_orgs.user_a.id),
        Post(title="B조직 공지", body="b", category="공지", org_id=two_orgs.org_b_id,
             author_user_id=two_orgs.user_b.id),
    ])
    db.commit()

    login_as("user", email="orgb@goodmit.co.kr")
    titles = {p["title"] for p in client.get("/api/board/posts").json()["items"]}

    assert "B조직 공지" in titles, "자기 조직 글이 안 보인다"
    assert "A조직 공지" not in titles, "다른 조직 게시글이 보인다"


def test_the_chat_directory_stays_inside_the_organization(client, login_as, two_orgs):
    """1:1 상대 고르기 목록에 **다른 회사 사람**이 나오면 안 된다 (1순위 유출 #7).

    부서로는 좁히지 않는다 — 다른 팀에 DM 을 못 보내게 되면 그건 기능 축소지 보안이 아니다.
    맞는 축은 조직이고, 이 목록은 이름·부서·직책을 그대로 준다(= 조직도 열거).
    """
    login_as("user", email="orgb@goodmit.co.kr")
    names = {u["display_name"] for u in client.get("/api/team-chat/directory").json()["users"]}

    assert "A사람" not in names, f"다른 조직 사람이 1:1 상대 목록에 나온다: {names}"


def test_the_assignee_picker_stays_inside_the_organization(client, login_as, two_orgs, db):
    """담당자 후보도 같다 (1순위 유출 #7). 검색은 사용자 종류를 역할로 막는데,
    이 목록이 그 결정을 옆문으로 무효화하고 있었다."""
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

    db.add(UserNotionMapping(user_id=two_orgs.user_a.id, notion_user_id="n-a",
                             status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=two_orgs.user_b.id, notion_user_id="n-b",
                             status=STATUS_VERIFIED))
    db.commit()

    login_as("user", email="orgb@goodmit.co.kr")
    names = {a["display_name"] for a in client.get("/api/tickets/assignees").json()["assignees"]}

    assert "B사람" in names, f"자기 조직 담당자 후보가 없다: {names}"
    assert "A사람" not in names, f"다른 조직 사람이 담당자 후보로 나온다: {names}"


def test_you_cannot_open_a_dm_with_someone_in_another_organization(
    client, login_as, two_orgs
):
    """1:1 대화 상대에 **조직 검증이 없었다** (3순위 IDOR).

    디렉터리를 조직으로 좁혀도(위) 이 경로는 `user_id` 를 그대로 받는다 — 목록에서 가린 것을
    id 를 직접 넣어 뚫는 전형적인 IDOR 다. 그리고 방을 **여는 순간** 그 방의 메시지·이미지
    접근권이 생긴다(이미지 서빙이 방 멤버십으로 판정하기 때문이다). 즉 목록만 가려서는
    아무 의미가 없다.

    **403 이 아니라 404** — 403 은 그 id 가 존재한다고 알려 준다(저장소 규칙).
    """
    csrf = login_as("user", email="orgb@goodmit.co.kr")
    r = client.post(
        "/api/team-chat/rooms/direct",
        json={"user_id": two_orgs.user_a.id},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404, (
        f"다른 조직 사람과 1:1 방이 열린다({r.status_code}) — "
        "여는 순간 그 방의 메시지·이미지 접근권이 생긴다"
    )


def test_you_can_still_dm_someone_in_your_own_organization(client, login_as, two_orgs, make_user, db):
    """같은 조직 안에서는 **부서가 달라도** 열려야 한다 — 다른 팀에 DM 을 못 보내면
    그건 기능 축소지 보안이 아니다."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    other_team = Department(name="A팀2", org_id=DEFAULT_ORG_ID)
    db.add(other_team)
    db.flush()
    mate = make_user("orga2@goodmit.co.kr", role="user", display_name="A사람2")
    mate.org_id = DEFAULT_ORG_ID
    mate.department_id = other_team.id
    db.commit()

    csrf = login_as("user", email="orga@goodmit.co.kr")
    r = client.post(
        "/api/team-chat/rooms/direct",
        json={"user_id": mate.id},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, f"같은 조직 다른 팀에 DM 을 못 연다: {r.status_code} {r.text[:120]}"


def test_the_notion_mapping_console_respects_scope(client, login_as, two_orgs, db):
    """같은 명부를 **옆문으로** 전부 볼 수 없다 (2순위 #2 / 3순위 IDOR).

    `/api/admin/users` 는 범위를 거는데 `/api/admin/notion-mapping` 은 안 걸었다 —
    같은 역할 게이트를 지나면서 같은 사람 목록(이메일 포함)을 그대로 내줬다.
    그리고 `/{user_id}` 경로들이 `get_scoped_user_or_404` 가 아니라 `get_user_or_404` 를
    썼다. 저장소가 **규칙으로 못박아 놓은** 것의 예외였다:

    > 관리자 라우터의 모든 `/{user_id}` 경로가 이 함수 하나를 통과해야 한다 — 한 군데라도
    > `get_user_or_404` 를 그대로 쓰면 그 경로만 범위를 무시한다.
    """
    from app.users.models import ROLE_ADMIN

    boss = two_orgs.user_b
    boss.role = ROLE_ADMIN
    db.commit()

    csrf = login_as("system_admin")
    r = client.patch(
        f"/api/admin/users/{boss.id}",
        json={"admin_scope": "org", "scope_org_id": two_orgs.org_b_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text

    login_as("admin", email="orgb@goodmit.co.kr")

    emails = {m["user_email"] for m in client.get("/api/admin/notion-mapping").json()["items"]}
    assert "orgb@goodmit.co.kr" in emails, "자기 조직 사람이 안 보인다"
    assert "orga@goodmit.co.kr" not in emails, "다른 조직 사람의 이메일이 매핑 화면에서 보인다"

    # 단건도 같아야 한다 — 목록에서 가린 것이 id 로 뚫리면 가린 의미가 없다.
    one = client.get(f"/api/admin/notion-mapping/{two_orgs.user_a.id}")
    assert one.status_code == 404, f"범위 밖 사용자의 매핑이 id 로 열린다: {one.status_code}"


def test_the_audit_log_does_not_show_other_organizations_activity(
    client, login_as, two_orgs, db, app
):
    """감사 로그는 **누가 무엇을 했나** 라서 행위자가 곧 축이다 (2순위 #3).

    범위 밖 사람의 행적이 보이면 목록 화면에서 가려 둔 것이 여기서 통째로 샌다 —
    그리고 CSV 내보내기까지 딸려 온다.

    시스템 행위(`user_id=None`)는 남긴다. 누구의 것도 아니고, 없애면 부서 관리자가 자기
    범위에서 일어난 자동 처리(보존 정리·동기화 실패 등)를 볼 수 없게 된다.
    """
    from app.audit.models import AuditLog
    from app.users.models import ROLE_ADMIN

    with app.state.session_factory() as s:
        s.add_all([
            AuditLog(action="user.update", object_type="user", object_id="x",
                     result="success", user_id=two_orgs.user_a.id),
            AuditLog(action="user.update", object_type="user", object_id="y",
                     result="success", user_id=two_orgs.user_b.id),
            AuditLog(action="retention.purge", object_type="system", object_id="-",
                     result="success", user_id=None),
        ])
        s.commit()

    boss = two_orgs.user_b
    boss.role = ROLE_ADMIN
    db.commit()
    csrf = login_as("system_admin")
    client.patch(f"/api/admin/users/{boss.id}",
                 json={"admin_scope": "org", "scope_org_id": two_orgs.org_b_id},
                 headers={"X-CSRF-Token": csrf})

    login_as("admin", email="orgb@goodmit.co.kr")
    rows = client.get("/api/admin/audit").json()["items"]
    actors = {r.get("user_id") for r in rows}
    actions = {r["action"] for r in rows}

    assert two_orgs.user_b.id in actors, "자기 조직 사람의 행적이 안 보인다"
    assert two_orgs.user_a.id not in actors, "다른 조직 사람의 행적이 보인다"
    assert "retention.purge" in actions, "시스템 행위가 사라졌다 — 자동 처리를 볼 수 없게 된다"

    # CSV 도 같은 필터여야 한다(그 파일 docstring 이 못박은 계약).
    text = client.get("/api/admin/audit/export.csv").text
    assert two_orgs.user_a.id not in text, "CSV 에는 다른 조직 사람의 행적이 그대로 나간다"


def test_the_department_list_stays_inside_the_organization(client, login_as, two_orgs, db):
    """조직도는 **다른 회사 것이 보이면 안 된다** (2순위 #1).

    부서 이름만으로도 그 회사가 무슨 일을 어떤 단위로 하는지 드러난다.
    `Department`/`JobTitle` 은 둘 다 `OrgScopedMixin` 을 상속한다 — **모델은 범위를 선언하는데
    질의가 안 걸고 있었다**(`trash_items` 와 같은 어긋남).
    """
    from app.users.models import ROLE_ADMIN

    boss = two_orgs.user_b
    boss.role = ROLE_ADMIN
    db.commit()
    csrf = login_as("system_admin")
    client.patch(f"/api/admin/users/{boss.id}",
                 json={"admin_scope": "org", "scope_org_id": two_orgs.org_b_id},
                 headers={"X-CSRF-Token": csrf})

    login_as("admin", email="orgb@goodmit.co.kr")
    names = {d["name"] for d in client.get("/api/admin/departments").json()["items"]}

    assert "B팀" in names, "자기 조직 부서가 안 보인다"
    assert "A팀" not in names, f"다른 조직의 조직도가 보인다: {names}"


def test_a_global_admin_still_sees_the_whole_org_chart(client, login_as, two_orgs):
    login_as("system_admin")
    names = {d["name"] for d in client.get("/api/admin/departments").json()["items"]}
    assert {"A팀", "B팀"} <= names, f"전체 관리자가 조직도를 다 못 본다: {names}"


def test_you_cannot_delete_another_organizations_department(client, login_as, two_orgs, db):
    """목록만 가려서는 소용없다 — **같은 함수를 수정·삭제 경로도 쓴다** (3순위 IDOR).

    범위를 안 걸면 다른 조직 부서를 **id 하나로 지울 수 있다.** 403 이 아니라 404 다.
    """
    from app.users.models import ROLE_ADMIN

    boss = two_orgs.user_b
    boss.role = ROLE_ADMIN
    db.commit()
    csrf = login_as("system_admin")
    client.patch(f"/api/admin/users/{boss.id}",
                 json={"admin_scope": "org", "scope_org_id": two_orgs.org_b_id},
                 headers={"X-CSRF-Token": csrf})

    csrf = login_as("admin", email="orgb@goodmit.co.kr")
    a_dept = two_orgs.dept_a.id

    assert client.get(f"/api/admin/departments/{a_dept}").status_code == 404, "단건이 열린다"
    r = client.patch(f"/api/admin/departments/{a_dept}", json={"name": "몰래 수정"},
                     headers={"X-CSRF-Token": csrf})
    assert r.status_code == 404, f"다른 조직 부서가 수정된다: {r.status_code}"
    r = client.delete(f"/api/admin/departments/{a_dept}", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 404, f"다른 조직 부서가 삭제된다: {r.status_code}"


def _scope_boss_to_org_b(client, login_as, two_orgs, db):
    from app.users.models import ROLE_ADMIN

    boss = two_orgs.user_b
    boss.role = ROLE_ADMIN
    db.commit()
    csrf = login_as("system_admin")
    r = client.patch(f"/api/admin/users/{boss.id}",
                     json={"admin_scope": "org", "scope_org_id": two_orgs.org_b_id},
                     headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    return login_as("admin", email="orgb@goodmit.co.kr")


def test_the_approval_queue_stays_inside_the_scope(client, login_as, two_orgs, db, app):
    """승인 큐에는 **역할 변경·설정 변경이 그대로 적혀 있다** (2순위 #4).

    요청자·대상·바뀌는 값이 다 들어 있어서, 다른 범위의 큐를 훑을 수 있으면 그 조직의
    인사·설정 변경을 실시간으로 들여다보는 셈이다.

    (감사 로그와 달리 `requested_by` 는 NOT NULL 이라 '시스템 요청' 예외가 없다.)
    """
    from app.approvals.models import Approval

    with app.state.session_factory() as s:
        s.add_all([
            Approval(request_type="user.role_change", object_type="user", object_id="x",
                     status="pending", requested_by=two_orgs.user_a.id),
            Approval(request_type="user.role_change", object_type="user", object_id="y",
                     status="pending", requested_by=two_orgs.user_b.id),
        ])
        s.commit()

    _scope_boss_to_org_b(client, login_as, two_orgs, db)
    ids = {a.get("requested_by") for a in client.get("/api/admin/approvals").json()["items"]}

    assert two_orgs.user_b.id in ids, "자기 조직 요청이 안 보인다"
    assert two_orgs.user_a.id not in ids, "다른 조직의 인사·설정 변경 요청이 보인다"


def test_you_cannot_read_another_scopes_ai_usage(client, login_as, two_orgs, db):
    """누가 얼마나 쓰는지는 **그 사람의 업무 강도이자 근태에 가깝다** (2순위 #5 / IDOR).
    `user_id` 를 그대로 받으면 목록에서 가린 것이 id 하나로 뚫린다."""
    _scope_boss_to_org_b(client, login_as, two_orgs, db)

    ok = client.get(f"/api/admin/ai-quotas/usage?user_id={two_orgs.user_b.id}")
    assert ok.status_code == 200, f"자기 조직 사람의 사용량을 못 본다: {ok.status_code}"

    r = client.get(f"/api/admin/ai-quotas/usage?user_id={two_orgs.user_a.id}")
    assert r.status_code == 404, f"다른 조직 사람의 AI 사용량이 조회된다: {r.status_code}"


def test_the_impersonation_history_stays_inside_the_scope(client, login_as, two_orgs, db, app):
    """이 표는 "**누가 누구의 계정으로 들어갔나**" 다 (2순위 #5).

    다른 조직의 이력을 볼 수 있으면 그 조직에 누가 있고 누가 관리자인지, 어떤 계정이 문제를
    겪었는지가 드러난다. **대상 기준**으로 좁힌다 — 보호받아야 하는 쪽은 당한 사람이다.
    """
    from app.impersonation.models import ImpersonationSession

    with app.state.session_factory() as s:
        s.add_all([
            ImpersonationSession(session_id="s-a", actor_user_id="x",
                                 target_user_id=two_orgs.user_a.id, reason="A조직 조사"),
            ImpersonationSession(session_id="s-b", actor_user_id="x",
                                 target_user_id=two_orgs.user_b.id, reason="B조직 조사"),
        ])
        s.commit()

    _scope_boss_to_org_b(client, login_as, two_orgs, db)
    targets = {r.get("target_user_id") for r in client.get("/api/admin/impersonation/sessions").json()["items"]}

    assert two_orgs.user_b.id in targets, "자기 조직 이력이 안 보인다"
    assert two_orgs.user_a.id not in targets, "다른 조직의 대리 보기 이력이 보인다"


def test_the_impersonation_history_stays_scoped_when_visible_users_exceed_one_sql_batch(
    client, login_as, two_orgs, db, app
):
    """UB-28: `visible_user_ids()`를 통째로 한 SQL IN(...)에 박으면 이 표의 문서화된
    목표 규모(scope.py::visible_user_ids 의 "~1000명" 주석)에서 SQLite 호스트 변수
    상한(빌드에 따라 999~32766)을 넘겨 이 조회가 처리 안 된 500이 될 수 있다. 조직 범위
    관리자가 보는 조직에 사람이 그만큼 있으면 재현된다 — `ID_BATCH_SIZE`를 넘는 인원을
    같은 조직에 두고도 스코프가 그대로 지켜지는지 확인한다."""
    from app.core.db import ID_BATCH_SIZE
    from app.impersonation.models import ImpersonationSession
    from app.users.models import ROLE_USER, User

    bulk_count = ID_BATCH_SIZE + 50
    with app.state.session_factory() as s:
        s.add_all([
            User(
                email=f"orgb-bulk-{i}@goodmit.co.kr", display_name=f"B팀원{i}",
                password_hash="not-a-real-hash", role=ROLE_USER, active=True,
                org_id=two_orgs.org_b_id,
            )
            for i in range(bulk_count)
        ])
        s.add_all([
            ImpersonationSession(session_id="s-a-scale", actor_user_id="x",
                                 target_user_id=two_orgs.user_a.id, reason="A조직 조사"),
            ImpersonationSession(session_id="s-b-scale", actor_user_id="x",
                                 target_user_id=two_orgs.user_b.id, reason="B조직 조사"),
        ])
        s.commit()

    _scope_boss_to_org_b(client, login_as, two_orgs, db)
    # 예전 코드라면 여기서 sqlite3.OperationalError("too many SQL variables")가 처리 안
    # 된 채 그대로 새서 200 대신 500이 났다.
    r = client.get("/api/admin/impersonation/sessions")
    assert r.status_code == 200, f"visible 집합이 커지자 조회 자체가 깨졌다: {r.status_code} {r.text}"
    targets = {row.get("target_user_id") for row in r.json()["items"]}

    assert two_orgs.user_b.id in targets, "자기 조직 이력이 청크 경계를 넘는 규모에서 안 보인다"
    assert two_orgs.user_a.id not in targets, "다른 조직의 대리 보기 이력이 새어 나왔다"


# UA-02: `_visible_ids`(sprints)와 `drop_out_of_scope_dtos`(tickets) 둘 다 예전엔
# `scope.is_dept`일 때만 걸러 org 범위 뷰어는 그대로 무제한(None)이었다. 이 세계의
# `two_orgs`는 org 범위(부서가 아니라)이므로 그 구멍을 정확히 재현한다.
@pytest.fixture()
def two_orgs_with_tickets(two_orgs, db, settings, fake_http, app):
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.tickets.sync import sync_tickets
    from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

    # 2026-07-14(화)가 기본 FakeClock now 다 — 그 주 [07-13, 07-20) 안에 마감을 둬야
    # `/api/assistant/weekly-digest`(query param 없이 항상 '이번 스프린트 창')에도 잡힌다.
    nid_a, nid_b = "notion-orgaxis-a", "notion-orgaxis-b"
    FakeNotionTasksDB(
        rows=[
            task_row(page_id="oa-a", tid=101, title="A조직 스프린트", status="진행",
                     due="2026-07-15", people=[nid_a], est_wd=2.0),
            task_row(page_id="oa-b", tid=102, title="B조직 스프린트", status="진행",
                     due="2026-07-16", people=[nid_b], est_wd=3.0),
        ],
        projects=[project_row(page_id="oa-p1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)
    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    db.add_all([
        UserNotionMapping(user_id=two_orgs.user_a.id, notion_user_id=nid_a, status=STATUS_VERIFIED),
        UserNotionMapping(user_id=two_orgs.user_b.id, notion_user_id=nid_b, status=STATUS_VERIFIED),
    ])
    db.commit()
    with app.state.session_factory() as s:
        sync_tickets(s, outbound=app.state.outbound_client, settings=settings,
                     now=app.state.clock.now())
        s.commit()
    return two_orgs


def test_org_scoped_sprint_summary_does_not_leak_the_other_organization(
    client, login_as, two_orgs_with_tickets, db
):
    _scope_boss_to_org_b(client, login_as, two_orgs_with_tickets, db)
    body = client.get("/api/sprint/summary?start=2026-07-01&end=2026-08-01").json()
    names = {d["name"] for d in body.get("developers", [])}
    assert "B사람" in names, f"자기 조직 담당자가 없다: {names}"
    assert "A사람" not in names, f"org 범위 뷰어에게 다른 조직 담당자 생산성이 보인다: {names}"


def test_org_scoped_weekly_digest_does_not_leak_the_other_organization(
    client, login_as, two_orgs_with_tickets, db
):
    """UA-01: `weekly_digest_facts`가 `visible_user_ids`를 안 넘겨 top_contributors가
    호출자의 조직과 무관하게 항상 전사였다."""
    _scope_boss_to_org_b(client, login_as, two_orgs_with_tickets, db)
    body = client.get("/api/assistant/weekly-digest").json()
    names = {c["name"] for c in body.get("top_contributors", [])}
    assert "B사람" in names, f"자기 조직 기여자가 없다: {names}"
    assert "A사람" not in names, f"org 범위 뷰어에게 다른 조직 기여자 명단이 보인다: {names}"


def test_the_job_queue_stays_inside_the_scope(client, login_as, two_orgs, db, app):
    """잡에는 **요청자의 입력이 payload 로 들어 있다** (2순위 #6) — 문서 생성 요청의 제목·기간,
    채팅 메시지 등. 큐를 훑는 것은 그 사람이 무엇을 요청했는지 읽는 것과 같다.

    시스템 잡(`user_id` 없음)은 남긴다 — 없애면 자기 범위의 자동 처리 실패를 못 본다.
    """
    from datetime import datetime, timezone

    from app.jobs.models import Job

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with app.state.session_factory() as s:
        s.add_all([
            Job(job_type="chat_message", payload_json="{}", user_id=two_orgs.user_a.id,
                available_at=now),
            Job(job_type="chat_message", payload_json="{}", user_id=two_orgs.user_b.id,
                available_at=now),
            Job(job_type="retention", payload_json="{}", user_id=None, available_at=now),
        ])
        s.commit()

    _scope_boss_to_org_b(client, login_as, two_orgs, db)
    rows = client.get("/api/admin/jobs").json()["items"]
    owners = {r.get("user_id") for r in rows}
    types = {r["job_type"] for r in rows}

    assert two_orgs.user_b.id in owners, "자기 조직 작업이 안 보인다"
    assert two_orgs.user_a.id not in owners, "다른 조직 사람의 작업 요청이 보인다"
    assert "retention" in types, "시스템 잡이 사라졌다 — 자동 처리 실패를 볼 수 없게 된다"
