"""프로젝트 API 가 **미러와 실제로 이어져 있는지**, 그리고 잘못된 입력에 500 을 내지 않는지.

진행률 계산 자체는 `tests/unit/test_project_progress.py` 가 순수 함수로 못박는다. 여기서
보는 것은 그 함수에 **무엇이 들어가는가**다 - 계산이 아무리 맞아도 표본이 틀리면 화면의
숫자는 틀린다. 그 다리는 세 곳에서 끊어질 수 있다:

  1. `project_ids` 는 구분자로 감싼 다중값 문자열이다. 토큰으로 안 감싸고 부분일치로
     찾으면 page id 접두사가 겹치는 **남의 프로젝트 티켓이 분모에 섞인다**.
  2. 0043 의 소프트 프룬(`notion_missing_at`)으로 목록에서 빠진 티켓을 진행률만 계속
     세면, 화면에 안 보이는 일이 분모에 남아 진행률이 이유 없이 낮게 나온다.
  3. Notion 짝이 없는 포털 전용 프로젝트에서 폴백으로 '전체 티켓'을 세면 회사의 모든
     작업이 그 프로젝트의 분모가 된다.

입력 쪽도 함께 본다. FK 와 NOT NULL 을 DB 에 맡기면 사용자는 400 이 아니라 **500** 을 보고,
화면은 "서버 오류"라고 말한다 - 아무도 자기 입력을 의심하지 않는다. 프로젝트 코드는 그
반대편에 있다. 코드는 서버가 짓고 사람은 고를 수 없으므로(D-282), 여기서 보는 것은 "잘못된
값을 막는가" 가 아니라 **"보내면 거절하고, 안 보내면 반드시 지어 주는가"** 다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.models_base import join_names
from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project
from app.tickets.models import TicketCache

pytestmark = pytest.mark.integration

NOW = datetime(2026, 7, 14, 0, 0, 0)
BOSS_EMAIL = "prj-api@goodmit.co.kr"

# 접두사가 겹치는 짝. 토큰으로 안 감싸면 `page-proj` 필터에 `page-proj-2` 가 따라온다.
PROJ_PAGE = "page-proj"
OTHER_PROJ_PAGE = "page-proj-2"


def _ticket(db, *, uid, page_id, projects, status="진행", est=None, missing_at=None,
            parent=None):
    row = TicketCache(
        id=uid,
        notion_page_id=page_id,
        org_id=DEFAULT_ORG_ID,
        title="작업",
        status=status,
        est_wd=est,
        parent_page_id=parent,
        project_ids=join_names(list(projects)),
        project_names="",
        assignee_notion_ids="",
        source="notion",
        synced_at=NOW,
        created_at=NOW,
        updated_at=NOW,
        notion_missing_at=missing_at,
    )
    db.add(row)
    return row


@pytest.fixture()
def world(db, make_user):
    boss = make_user(BOSS_EMAIL, role="admin", display_name="관리자")
    boss.admin_scope = "global"
    db.commit()

    linked = Project(
        name="노션에 짝이 있는 프로젝트", org_id=DEFAULT_ORG_ID, notion_page_id=PROJ_PAGE,
    )
    portal_only = Project(name="포털 전용 프로젝트", org_id=DEFAULT_ORG_ID)
    db.add_all([linked, portal_only])
    db.commit()
    return {"linked": linked.id, "portal_only": portal_only.id}


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS_EMAIL)}


def test_progress_counts_only_this_projects_tickets(client, login_as, db, world):
    """다중값 열을 토큰으로 감싸 맞추는지 - 접두사가 겹치는 프로젝트가 섞이면 안 된다."""
    _ticket(db, uid="t-mine-done", page_id="p-1", projects=(PROJ_PAGE,),
            status="완료", est=3)
    _ticket(db, uid="t-mine-open", page_id="p-2", projects=(PROJ_PAGE,),
            status="진행", est=7)
    _ticket(db, uid="t-other", page_id="p-3", projects=(OTHER_PROJ_PAGE,),
            status="완료", est=90)
    db.commit()

    body = client.get(
        f"/api/projects/{world['linked']}/progress", headers=_hdr(login_as)
    ).json()

    assert body["basis"]["counted_tasks"] == 2, (
        f"남의 프로젝트 티켓이 분모에 섞였다: {body['basis']}"
    )
    assert body["percent"] == 30.0, f"3 / (3 + 7) 이 아니다: {body}"


def test_softly_pruned_tickets_leave_the_denominator(client, login_as, db, world):
    """0043 이 '안 보임'으로 표시한 티켓은 목록에서 이미 빠져 있다.

    진행률만 계속 세면 화면에 없는 일이 분모에 남아 진행률이 이유 없이 낮아진다.
    그리고 다음 회차에 돌아오면 표시가 지워져 아무 일도 없었던 것이 된다 - 그때 숫자가
    저절로 바뀌면 아무도 원인을 못 찾는다.
    """
    _ticket(db, uid="t-live", page_id="p-1", projects=(PROJ_PAGE,), status="완료", est=5)
    _ticket(db, uid="t-gone", page_id="p-2", projects=(PROJ_PAGE,), status="진행",
            est=5, missing_at=NOW)
    db.commit()

    body = client.get(
        f"/api/projects/{world['linked']}/progress", headers=_hdr(login_as)
    ).json()

    assert body["basis"]["counted_tasks"] == 1, (
        f"소프트 프룬된 티켓이 분모에 남아 있다: {body['basis']}"
    )
    assert body["percent"] == 100.0


def test_a_portal_only_project_counts_nothing_rather_than_everything(
    client, login_as, db, world
):
    """Notion 짝이 없으면 걸린 작업이 있을 수 없다. 폴백으로 전체를 세면 안 된다."""
    _ticket(db, uid="t-somebody", page_id="p-1", projects=(PROJ_PAGE,),
            status="완료", est=5)
    db.commit()

    body = client.get(
        f"/api/projects/{world['portal_only']}/progress", headers=_hdr(login_as)
    ).json()

    assert body["basis"]["sample_tasks"] == 0, (
        f"포털 전용 프로젝트가 남의 작업을 세고 있다: {body['basis']}"
    )
    assert body["percent"] is None, "셀 것이 없는데 0% 라고 답한다"


def test_the_child_and_the_parent_are_not_counted_twice(client, login_as, db, world):
    """미러의 `parent_page_id` 가 관계 표를 지나 리프 판정까지 실제로 이어지는지 (S6)."""
    from app.work import relations

    _ticket(db, uid="t-parent", page_id="page-parent", projects=(PROJ_PAGE,),
            status="진행", est=100)
    _ticket(db, uid="t-child", page_id="page-child", projects=(PROJ_PAGE,),
            status="완료", est=10, parent="page-parent")
    db.flush()
    # 계층의 정본은 `ticket_relations` 다. 동기화가 부르는 그 함수를 여기서도 부른다 —
    # 관계 행을 손으로 넣으면 파생이 실제로 도는지는 아무도 안 본다.
    relations.sync_parent_links(db)
    db.commit()

    body = client.get(
        f"/api/projects/{world['linked']}/progress", headers=_hdr(login_as)
    ).json()

    assert body["basis"]["parent_tasks_excluded"] == 1, (
        f"부모가 분모에 남았다(이중 계산): {body['basis']}"
    )
    assert body["percent"] == 100.0


def test_recompute_caches_the_percent_on_the_row(client, login_as, db, world):
    """목록이 프로젝트마다 티켓을 다시 세지 않도록 캐시한다."""
    _ticket(db, uid="t-1", page_id="p-1", projects=(PROJ_PAGE,), status="완료", est=1)
    _ticket(db, uid="t-2", page_id="p-2", projects=(PROJ_PAGE,), status="진행", est=3)
    db.commit()

    assert db.get(Project, world["linked"]).progress_pct is None, (
        "계산 전에는 NULL 이어야 한다 - 0.0 은 '셌는데 0%' 라는 뜻이다"
    )

    r = client.post(
        f"/api/projects/{world['linked']}/progress/recompute", headers=_hdr(login_as)
    )
    assert r.status_code == 200, r.text

    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert db.get(Project, world["linked"]).progress_pct == 25.0


def test_the_client_cannot_choose_the_code_and_the_server_always_gives_one(
    client, login_as, world
):
    """코드는 서버가 짓고 사람은 고를 수 없다 (D-282).

    보내온 `code` 를 조용히 버리지 않고 422 로 거절한다. 버리면 보낸 쪽은 자기가 고른
    코드가 들어갔다고 믿고, 그 믿음은 화면에 다른 코드가 뜰 때까지 안 깨진다 — 그 사이
    옛 코드로 만든 링크를 사람들에게 뿌린다.

    반대로 안 보냈을 때는 **반드시** 정책에 맞는 코드가 붙어 나와야 한다. 코드가 비어
    있으면 그 프로젝트의 티켓은 `<CODE>-<SEQ>` 라는 이름을 가질 수 없고, 이름이 없는
    티켓은 대화에서도 문서에서도 가리킬 방법이 없다.
    """
    from app.work import codes

    hdr = _hdr(login_as)
    supplied = client.post(
        "/api/projects", json={"name": "가", "code": "ABCDEF"}, headers=hdr
    )
    assert supplied.status_code == 422, (
        f"클라이언트가 프로젝트 코드를 정할 수 있다: {supplied.status_code} {supplied.text}"
    )

    made = client.post("/api/projects", json={"name": "나"}, headers=hdr)
    assert made.status_code == 200, made.text
    minted = made.json()["project"]["code"]
    assert codes.is_valid(minted), f"서버가 지은 코드가 정책과 다르다: {minted!r}"


@pytest.mark.real_db  # 스레드/별도 세션이 이 시험의 데이터를 봐야 한다 (D-190)
def test_two_concurrent_creations_both_succeed_with_different_codes(app, login_as, world):
    """PROJ-01 의 뒤집힌 판정 (D-282).

    사용자가 코드를 고르던 시절에는 같은 코드로 동시에 온 두 요청 중 하나가 409 를 받는
    것이 정답이었다. 이제 코드를 고르는 사람이 없다 — 서버가 행의 uuid 에서 파생하므로
    두 요청은 애초에 다른 코드를 짓고, 따라서 **둘 다 성공해야 한다.** 여기서 한쪽이
    실패하면 사용자는 자기가 아무것도 고르지 않은 값 때문에 거절당한 셈이라 무엇을
    고쳐야 하는지 알 수 없다.

    그래도 동시성을 실제로 겹쳐 봐야 하는 이유는 INSERT 다. 두 INSERT 가 진짜로 겹칠 때만
    유니크 위반이 세션을 망가뜨리는 경로(500)와 두 프로젝트가 같은 코드를 갖는 경로가
    드러난다. `threading.Barrier(2)` 를 INSERT 직전에 세워(test_prompt_create_new_version_
    race.py 와 동일 기법) 둘이 같은 순간에 DB 로 들어가게 만든다.
    """
    import threading

    from fastapi.testclient import TestClient
    from sqlalchemy import event

    from app.work import codes
    from tests.conftest import DEFAULT_TEST_PASSWORD

    login_as("admin", email=BOSS_EMAIL)  # 관리자 계정을 미리 만들어 둔다.
    engine = app.state.engine
    barrier = threading.Barrier(2)
    hits = 0
    hits_lock = threading.Lock()

    def _pause_before_insert_races(conn, cursor, statement, parameters, context, executemany):
        nonlocal hits
        if "INSERT INTO projects" not in statement or "동시생성" not in str(parameters):
            return
        with hits_lock:
            hits += 1
            should_wait = hits <= 2
        if should_wait:
            barrier.wait(timeout=5)

    def attempt(i):
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post("/login", json={"email": BOSS_EMAIL, "password": DEFAULT_TEST_PASSWORD})
            assert r.status_code == 200, r.text
            token = r.json()["csrf_token"]
            resp = c.post(
                "/api/projects", json={"name": f"동시생성{i}"},
                headers={"X-CSRF-Token": token},
            )
            body = resp.json() if resp.status_code == 200 else {}
            return resp.status_code, body.get("project", {}).get("code")

    event.listen(engine, "before_cursor_execute", _pause_before_insert_races)
    try:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
    finally:
        event.remove(engine, "before_cursor_execute", _pause_before_insert_races)

    # 이 시험이 정말로 겹치게 만들었는지 먼저 묻는다. 필터가 INSERT 를 못 잡으면 아무도
    # 기다리지 않고 두 요청은 그냥 차례로 지나가는데, 그때도 아래 단언은 전부 통과한다 —
    # 경합을 한 번도 안 본 초록이다.
    assert hits >= 2, f"INSERT 를 못 잡아 경합이 만들어지지 않았다: hits={hits}"

    statuses = [status for status, _ in results]
    minted = [code for _, code in results]
    assert statuses == [200, 200], (
        f"코드를 고른 사람이 없는데 한쪽이 거절당했다(409 든 500 이든): {results}"
    )
    assert all(codes.is_valid(code) for code in minted), (
        f"경합 뒤에 정책과 다른 코드가 남았다: {minted}"
    )
    assert len(set(minted)) == 2, (
        f"동시에 만든 두 프로젝트가 같은 코드를 받았다 — 티켓 이름이 겹친다: {minted}"
    )


def test_every_new_project_comes_back_with_its_own_code(client, login_as, world):
    """코드 없는 프로젝트는 이제 만들어지지 않는다 (D-282).

    예전에는 코드가 선택이라 NULL 인 프로젝트가 정상 상태였다. 지금은 서버가 생성 때마다
    짓는다 — 그래서 여기서 볼 것이 뒤집혔다. "NULL 끼리 안 부딪히는가" 가 아니라 **"두
    프로젝트가 서로 다른 코드를 받았는가"** 다. 둘이 같은 코드를 받으면 그 순간부터 두
    프로젝트의 티켓이 같은 이름을 쓰고, 링크를 눌렀을 때 어느 쪽이 열릴지 아무도 답할 수
    없다.
    """
    from app.work import codes

    hdr = _hdr(login_as)
    first = client.post("/api/projects", json={"name": "코드 하나"}, headers=hdr)
    second = client.post("/api/projects", json={"name": "코드 둘"}, headers=hdr)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    minted = [first.json()["project"]["code"], second.json()["project"]["code"]]
    assert all(codes.is_valid(code) for code in minted), (
        f"코드가 비었거나 정책과 다르다: {minted}"
    )
    assert minted[0] != minted[1], f"두 프로젝트가 같은 코드를 받았다: {minted}"


def test_an_unknown_department_is_404_not_500(client, login_as, world):
    """FK 에 맡기면 IntegrityError 가 500 으로 나가고, FK 가 꺼진 환경이면 어느 부서
    목록에도 안 나오는 유령 행이 남는다. 범위 밖 부서와 **같은 404** 여야 한다."""
    r = client.post(
        "/api/projects",
        json={"name": "유령", "dept_id": "there-is-no-such-department"},
        headers=_hdr(login_as),
    )
    assert r.status_code == 404, f"없는 부서로 프로젝트가 만들어진다: {r.status_code} {r.text}"


def test_blanking_a_required_field_is_422_not_500(client, login_as, world):
    """NOT NULL 컬럼에 명시적 null 을 넣으면 400 대가 나와야 한다."""
    r = client.patch(
        f"/api/projects/{world['linked']}", json={"name": None}, headers=_hdr(login_as)
    )
    assert r.status_code == 422, f"이름을 비웠는데 {r.status_code} 다: {r.text}"


def test_progress_is_not_settable_from_the_client(client, login_as, world):
    """`progress_pct` 를 입력으로 받으면 화면이 보고 싶은 숫자를 써 넣을 수 있다.

    그러면 "앱이 다시 계산한다"는 이 subsystem 의 전제가 그 자리에서 무너진다 - 틀린 것보다
    나쁘다(틀린 줄도 모른다).
    """
    r = client.patch(
        f"/api/projects/{world['linked']}",
        json={"progress_pct": 99.0},
        headers=_hdr(login_as),
    )
    assert r.status_code == 422, f"클라이언트가 진행률을 직접 넣을 수 있다: {r.status_code}"


def test_the_code_is_not_settable_from_the_client(client, login_as, world):
    """코드를 바꾸는 입구는 제품 어디에도 없다 (D-282).

    코드가 바뀌면 그 프로젝트 티켓 전부의 이름(`<CODE>-<SEQ>`)이 함께 바뀐다. 그 이름은
    이미 문서와 대화와 메일에 뿌려져 있어서, 바꾼 순간 어제 공유한 링크가 아무 데도 닿지
    않는다 — 그리고 그것을 되돌릴 방법이 없다. 그래서 수정 본문에 실려 온 `code` 는
    진행률과 **같은 이유로** 422 다.
    """
    r = client.patch(
        f"/api/projects/{world['linked']}",
        json={"code": "ABCDEF"},
        headers=_hdr(login_as),
    )
    assert r.status_code == 422, f"클라이언트가 프로젝트 코드를 바꿀 수 있다: {r.status_code}"


def test_renaming_a_project_leaves_its_code_alone(client, login_as, db, world):
    """이름을 바꿔도 코드는 한 글자도 안 움직인다 (D-282).

    앞 정책은 사람이 이름을 보고 코드를 정했고, 그래서 소스의 이름이 바뀐 날 확정해 둔
    20건이 **전부** 못 찾는 값이 됐다(옛 D-278). 지금 코드는 이름이 아니라 행의 씨앗에서
    나오므로 이름은 얼마든지 바꿔도 된다 — 이 시험이 그 자유를 지킨다.

    응답만 보지 않고 행까지 다시 읽는 이유는, 응답이 수정 전 값을 그대로 되돌려 주면서
    행은 바뀌어 있는 경우를 응답만으로는 구별할 수 없기 때문이다.
    """
    hdr = _hdr(login_as)
    made = client.post("/api/projects", json={"name": "옛 이름"}, headers=hdr)
    assert made.status_code == 200, made.text
    project_id = made.json()["project"]["id"]
    before = made.json()["project"]["code"]

    renamed = client.patch(
        f"/api/projects/{project_id}", json={"name": "새 이름"}, headers=hdr
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["project"]["name"] == "새 이름", (
        "이름이 안 바뀌었다면 이 시험은 코드가 안 움직였다는 것을 확인한 것이 아니다"
    )
    assert renamed.json()["project"]["code"] == before, (
        f"이름을 바꿨더니 코드가 따라 바뀌었다: {before} → {renamed.json()['project']['code']}"
    )

    db.commit()  # 스냅샷을 새로 뜬다 — 위 recompute 시험과 같은 이유다
    db.expire_all()
    assert db.get(Project, project_id).code == before, (
        "응답은 옛 코드를 말하는데 행은 바뀌어 있다 — 화면과 DB 가 갈렸다"
    )
